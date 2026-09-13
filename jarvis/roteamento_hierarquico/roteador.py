# Motor de roteamento hierárquico de ferramentas, em duas etapas,
# sobre a Groq (SEM ESTADO — cada processar_turno() é uma conversa
# isolada, sem sessão persistente no servidor). Ver
# jarvis/roteamento_hierarquico/config.py para o porquê deste módulo
# ser standalone e não plugado a nenhum dos dois cérebros de voz
# atuais (Gemini Live / OpenAI Realtime) ainda.
#
# QUEM FALA COM A GROQ é jarvis/servicos/agentes/ (LangChain), não
# mais um requests.post escrito aqui. O que mudou de lugar, e o que
# não mudou:
#
#   - A lógica de REPETIÇÃO continua sendo desta etapa, mas agora é
#     declarada (_POLITICA) em vez de implementada: os dois
#     orçamentos independentes, a espera que respeita o retry-after
#     do servidor e o teto dessa espera viraram uma PoliticaRepeticao.
#     Nada foi afrouxado — os valores continuam vindo de config.py.
#   - O PLANO B (refazer a etapa 1 sem o histórico) continua aqui,
#     porque ele é decisão DESTE roteador, não de uma chamada
#     genérica: só quem sabe que a etapa 1 manda catálogo e espera
#     texto sabe que remover o histórico é a última cartada certa.
#   - A distinção entre os erros deixou de ser lida do status HTTP e
#     passou a vir de resposta.tipo_erro. Ver
#     jarvis/servicos/agentes/erros.py, que guarda inteiro o porquê
#     de 429 e "tool choice is none" serem os únicos casos que valem
#     repetir.
#
# LIMITAÇÃO CONHECIDA, documentada de propósito: alguns pacotes
# (rede_jarvis, admin_terminal, discord_jarvis, chat_jarvis,
# clique_visual) só funcionam por completo porque
# GeminiLiveWorker.__init__ chama seus inicializadores de sessão
# (iniciar_rede_jarvis(), etc.) e registra callbacks de fala
# espontânea. Chamar processar_turno() num processo onde nenhum
# GeminiLiveWorker jamais foi construído significa que esses pacotes
# específicos podem despachar mas se comportar de forma incompleta
# (ex.: uma confirmação de permissão remota sem callback de voz
# registrado). Quem for plugar este módulo num pipeline completo
# (como o do servidor dedicado STT/TTS via MQTT) precisa chamar os
# mesmos inicializadores no processo novo antes de usar isto a
# sério.
import re

from jarvis.nucleo import prompts
from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS
from jarvis.servicos import agentes

from . import catalogo
from . import config
from . import esquema_groq

# Reconhece "FERRAMENTAS: nome1, nome2" como a ÚNICA linha não vazia
# da resposta da etapa 1 — qualquer outra coisa na resposta é tratada
# como resposta direta do usuário (nunca uma mistura dos dois).
_PADRAO_MARCADOR = re.compile(
    r"^\s*FERRAMENTAS\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


# Os dois orçamentos de repetição, INDEPENDENTES, porque são dois
# problemas diferentes: o 429 é do servidor e pede espera; o 400 de
# tool call indevida é do modelo e pede só outra amostragem. Somar os
# dois num contador só faria um rate limit consumir as tentativas
# reservadas para o outro caso.
#
# Medido ao vivo neste projeto: o tier gratuito do openai/gpt-oss-20b
# tem teto de 8000 tokens por MINUTO e cada chamada da etapa 1 custa
# ~1450 tokens (o catálogo inteiro vai no prompt toda vez) — ~5 turnos
# por minuto antes de estourar, o que um ritmo normal de conversa
# ultrapassa fácil. O corpo do 429 vem com "Please try again in 975ms",
# então a janela reabre em ~1s: repetir resolve, esperar o usuário
# repetir a frase não.
_POLITICA = agentes.PoliticaRepeticao(
    tentativas_limite=config.TENTATIVAS_RATE_LIMIT,
    tentativas_ferramenta_indevida=config.TENTATIVAS_TOOL_CALL_INDEVIDA,
    espera_base=config.ESPERA_BASE_RATE_LIMIT,
    espera_maxima=config.ESPERA_MAXIMA_RATE_LIMIT,
    rotulo="roteamento_hierarquico",
)


# Uma etapa executada, pra quem for medir custo/latência (requisito
# 6) — nunca usado pra tomar decisão dentro do próprio roteador.
class EtapaExecutada:
    def __init__(self, numero, modelo, usage, latencia_segundos):
        self.numero = numero
        self.modelo = modelo
        self.usage = usage or {}
        self.latencia_segundos = latencia_segundos


# Resultado final de um turno — o texto pronto pra ser falado
# (resposta), mais os metadados de como se chegou até ele.
class ResultadoTurno:
    def __init__(
        self,
        resposta,
        usou_ferramenta=False,
        ferramenta_executada=None,
        pedido_esclarecimento=False,
        falhou=False,
    ):
        self.resposta = resposta
        self.usou_ferramenta = usou_ferramenta
        self.ferramenta_executada = ferramenta_executada
        self.pedido_esclarecimento = pedido_esclarecimento

        # O ROTEAMENTO em si não pôde ser feito (sem chave, a Groq
        # falhou, o catálogo não carregou). Diferente de
        # usou_ferramenta=False, que significa "rodou e concluiu que
        # era conversa" — o oposto disto.
        #
        # BUG REAL que motivou este campo: quem consome este resultado
        # não tinha como separar as duas coisas, porque a falha vinha
        # codificada só como prosa em .resposta. O worker de voz local
        # tratava toda falha de roteamento como conversa e mandava a
        # fala para o servidor de voz, que não sabe que ferramentas
        # existem e respondia algo plausível ("claro, abrindo o
        # navegador") sem nada ter sido executado. O usuário reportou
        # exatamente isso: pediu para abrir o navegador, ouviu que
        # estava abrindo, e nada abriu — na segunda tentativa, com a
        # janela de rate limit já reaberta, funcionou.
        #
        # Um pedido pode perfeitamente ter sido uma ferramenta: falhar
        # o roteamento NUNCA pode virar conversa em silêncio.
        self.falhou = falhou

        self.etapas = []

    def total_tokens(self):
        return sum(
            etapa.usage.get("total_tokens", 0) for etapa in self.etapas
        )


# Monta o pedido de uma etapa. As duas etapas só diferem em três
# coisas — a instrução de sistema, o modelo e se declaram ferramentas
# — então o resto (histórico, mensagem do usuário, timeout) é montado
# uma vez só, aqui.
def _pedido_groq(
    instrucao_sistema,
    mensagem_usuario,
    modelo,
    historico=None,
    ferramentas=None,
):
    return agentes.PedidoAgente(
        provedor="groq",
        modelo=modelo,
        api_key=config.GROQ_API_KEY,
        texto=mensagem_usuario,
        instrucao_sistema=instrucao_sistema,
        historico=historico,
        ferramentas=ferramentas,
        timeout=config.TIMEOUT_SEGUNDOS,
    )


# Executa um pedido com a política de repetição deste módulo. Nunca
# levanta — devolve sempre uma RespostaAgente, de sucesso ou de
# falha.
def _consultar(pedido):
    return agentes.executar(pedido, _POLITICA)


# Registra uma etapa já executada no resultado, com o uso de tokens no
# formato de chave do provedor — é esse formato que
# medir_custo.py lê para calcular cache hit (prompt_tokens_details.
# cached_tokens só existe nele).
def _registrar_etapa(resultado, numero, modelo, resposta):
    resultado.etapas.append(
        EtapaExecutada(
            numero,
            modelo,
            resposta.uso.como_dicionario_provedor(),
            resposta.latencia_segundos,
        )
    )


# Extrai e valida os nomes candidatos do texto do marcador — só
# nomes que existem de verdade no catálogo curto, sem duplicatas,
# preservando a ordem em que o modelo os citou, e cortado no limite
# configurado.
def _extrair_candidatos_validos(texto_marcador):
    nomes_brutos = [
        nome.strip() for nome in texto_marcador.split(",") if nome.strip()
    ]

    vistos = {}

    for nome in nomes_brutos:
        if nome in catalogo.CATALOGO_CURTO:
            vistos.setdefault(nome, None)

    return list(vistos.keys())[: config.LIMITE_FERRAMENTAS_CANDIDATAS]


# Agrupa os candidatos por categoria — usado pra decidir se dá pra
# seguir direto pra etapa 2 (uma categoria só) ou se é preciso pedir
# esclarecimento (mais de uma).
def _categorias_dos_candidatos(nomes_candidatos):
    return {catalogo.CATALOGO_CURTO[nome][0] for nome in nomes_candidatos}


def _pedido_esclarecimento(nomes_candidatos):
    opcoes = "; ".join(
        f"{nome} ({catalogo.CATALOGO_CURTO[nome][1]})"
        for nome in nomes_candidatos
    )

    return (
        "Não ficou claro qual dessas ações você quer — pode ser: "
        f"{opcoes}. Pode especificar melhor o que precisa?"
    )


# Despacha nome_funcao/argumentos pelo mesmo loop de
# PACOTES_REGISTRADOS que jarvis/cerebro/gemini/cliente_live.py já usa —
# sem nenhum estado de worker/sessão, exatamente como esses pacotes
# já são chamados hoje. Devolve None se nenhum pacote reconhecer o
# nome (não deveria acontecer, já que o nome veio do próprio
# catálogo, mas é tratado de forma defensiva mesmo assim).
def _despachar(nome_funcao, argumentos):
    for pacote in PACOTES_REGISTRADOS:
        try:
            resultado = pacote.despachar(nome_funcao, argumentos)

        except Exception as erro:
            print(
                f"[roteamento_hierarquico] Erro ao despachar "
                f"'{nome_funcao}': {erro}"
            )

            return (
                "Não consegui executar essa ação agora — houve um "
                "erro interno."
            )

        if resultado is not None:
            return resultado

    return None


# Ponto de entrada principal. mensagem_usuario é o texto já
# transcrito (este módulo não faz STT). historico, se dado, é uma
# lista de {"role": "user"|"assistant", "content": str} de turnos
# anteriores — o CHAMADOR decide quanto contexto incluir; este
# módulo não guarda estado entre chamadas.
# preparar_argumentos, quando dado, é chamado com
# (nome_funcao, argumentos) logo ANTES do despacho e devolve os
# argumentos a usar. Existe porque algumas ferramentas precisam de um
# dado que só o CLIENTE consegue produzir — hoje, a imagem da câmera
# de identificar_planta e consultar_segunda_opiniao_visual, que no
# cliente do Gemini é capturada e injetada em args antes do despacho
# (ver processar_chamada_de_funcao em jarvis/cerebro/gemini/cliente_live.py).
#
# Sem este gancho, essas duas eram alcançáveis pelo roteamento mas
# falhavam sempre, com "nenhuma imagem foi capturada": o catálogo as
# oferece, o pacote as reconhece, e ninguém tinha por onde entregar a
# imagem. A alternativa seria o pacote se virar sozinho, mas isso
# mudaria o comportamento dele também no caminho do Gemini, onde a
# captura é feita sob mutex pelo cliente de propósito.
def processar_turno(
    mensagem_usuario,
    historico=None,
    preparar_argumentos=None,
):
    historico = historico or []

    if not config.GROQ_API_KEY:
        return ResultadoTurno(
            "GROQ_API_KEY não configurada no .env.",
            falhou=True,
        )

    # --- ETAPA 1: catálogo curto, prefixo fixo ---
    pedido_etapa1 = _pedido_groq(
        prompts.ROTEAMENTO_ETAPA1_INSTRUCAO.format(
            catalogo=catalogo.TEXTO_CATALOGO
        ),
        mensagem_usuario,
        config.MODELO_GROQ_ETAPA1,
        historico=historico,
    )

    resposta_etapa1 = _consultar(pedido_etapa1)

    # PLANO B, e ele ataca a causa em vez de sortear de novo.
    #
    # O 400 de "o modelo chamou uma ferramenta" acontece muito mais com
    # HISTÓRICO na conversa: medido com a frase do caso relatado, 0 em 8
    # sem nenhum turno anterior, e de 1 a 3 em cada 6 com um turno de
    # assistente antes. As repetições dentro da camada de agentes
    # reenviam a mesma mensagem e por isso continuam esbarrando no mesmo
    # gatilho — em 5 turnos reais, um esgotou as três.
    #
    # Aqui a última cartada é remover o gatilho: refaz a etapa 1 SEM o
    # histórico. Perde-se contexto (um "e o segundo?" deixa de ser
    # entendido como continuação), e é uma troca que só acontece depois
    # de a chamada normal já ter falhado — perder contexto é muito
    # melhor do que perder o turno inteiro, que é o que o usuário viu.
    if (
        not resposta_etapa1.sucesso
        and historico
        and resposta_etapa1.tipo_erro == agentes.erros.FERRAMENTA_INDEVIDA
    ):
        print(
            "[roteamento_hierarquico] A etapa 1 falhou mesmo repetindo; "
            "tentando sem o histórico da conversa."
        )

        resposta_etapa1 = _consultar(pedido_etapa1.sem_historico())

    if not resposta_etapa1.sucesso:
        # falhou=True: o roteamento NÃO rodou. Quem chama não pode
        # tratar isto como "era conversa" — o pedido pode muito bem
        # ter sido uma ferramenta.
        return ResultadoTurno(
            f"Não consegui processar seu pedido agora: "
            f"{resposta_etapa1.erro}",
            falhou=True,
        )

    resultado = ResultadoTurno(resposta_etapa1.texto)
    _registrar_etapa(
        resultado, 1, config.MODELO_GROQ_ETAPA1, resposta_etapa1
    )

    marcador = _PADRAO_MARCADOR.match(resposta_etapa1.texto)

    if not marcador:
        # Nenhuma ferramenta apontada — a resposta da etapa 1 já É a
        # resposta final. Zero segunda chamada (requisito 3).
        return resultado

    nomes_candidatos = _extrair_candidatos_validos(marcador.group(1))

    if not nomes_candidatos:
        # Marcador reconhecido, mas nenhum nome válido dentro dele —
        # nunca adivinha: pede pro usuário repetir, sem gastar uma
        # segunda chamada num schema que nem se sabe qual seria.
        resultado.resposta = (
            "Entendi que você quer que eu faça algo, mas não "
            "identifiquei qual ação — pode repetir de outro jeito?"
        )
        resultado.pedido_esclarecimento = True

        return resultado

    if len(_categorias_dos_candidatos(nomes_candidatos)) > 1:
        # Ambiguidade entre categorias diferentes: nunca escolhe
        # sozinho (mesmo padrão usado em todo o resto do projeto —
        # esquecer_memoria, fechar_app, resolução de contato do
        # Discord, etc.). Ver decisão de design no plano: um critério
        # de "categoria mais específica" não teria sinal real sobre a
        # intenção do usuário nesta mensagem específica.
        resultado.resposta = _pedido_esclarecimento(nomes_candidatos)
        resultado.pedido_esclarecimento = True

        return resultado

    # --- ETAPA 2: schema completo, só dos candidatos ---
    esquemas = esquema_groq.obter_schemas_completos(
        nomes_candidatos, PACOTES_REGISTRADOS
    )

    if not esquemas:
        # Os nomes existem no catálogo, mas nenhum pacote registrado
        # os reconheceu de verdade — catálogo desatualizado (ver
        # catalogo.verificar_catalogo_atualizado). Não adivinha.
        resultado.resposta = (
            "Entendi que ação seria, mas não consegui carregar os "
            "detalhes dela agora — pode tentar de novo?"
        )
        resultado.falhou = True

        return resultado

    resposta_etapa2 = _consultar(
        _pedido_groq(
            prompts.ROTEAMENTO_ETAPA2_INSTRUCAO.format(
                ferramentas=", ".join(nomes_candidatos)
            ),
            mensagem_usuario,
            config.MODELO_GROQ_ETAPA2,
            historico=historico,
            ferramentas=esquemas,
        )
    )

    if not resposta_etapa2.sucesso:
        # A etapa 1 JÁ tinha decidido que era ferramenta, então isto é
        # ainda mais claramente uma falha — nunca uma conversa.
        resultado.resposta = (
            f"Não consegui concluir essa ação agora: "
            f"{resposta_etapa2.erro}"
        )
        resultado.falhou = True

        return resultado

    _registrar_etapa(
        resultado, 2, config.MODELO_GROQ_ETAPA2, resposta_etapa2
    )

    chamada = resposta_etapa2.primeira_chamada()

    if chamada is None:
        # O modelo, já vendo os detalhes completos, decidiu que
        # nenhuma ferramenta realmente serve — o texto dele vira a
        # resposta final, mesmo tratamento da etapa 1.
        resultado.resposta = resposta_etapa2.texto

        return resultado

    # No máximo UMA chamada por turno — mesma suposição de "uma ação
    # por pedido" já usada em todo o projeto (ex.: clicar_elemento_
    # visual). Se o modelo devolver mais de uma, só a primeira roda;
    # é o que primeira_chamada() garante.
    nome_funcao = chamada.nome
    argumentos = esquema_groq.interpretar_argumentos(chamada.argumentos)

    # Enriquecimento dos argumentos pelo chamador (ex.: capturar a
    # imagem da câmera). Uma falha aqui não pode derrubar o turno nem
    # deixar a ferramenta rodar sem o dado que ela precisa.
    if preparar_argumentos is not None:
        try:
            argumentos = preparar_argumentos(nome_funcao, argumentos)

        except Exception as erro:
            print(
                "[roteamento_hierarquico] preparar_argumentos falhou "
                f"para '{nome_funcao}': {erro}"
            )

            resultado.resposta = (
                "Não consegui preparar o que essa ação precisava "
                f"({erro})."
            )
            resultado.falhou = True

            return resultado

    resultado_despacho = _despachar(nome_funcao, argumentos)

    if resultado_despacho is None:
        resultado.resposta = (
            f"A ferramenta '{nome_funcao}' não foi reconhecida por "
            "nenhum pacote registrado."
        )
        resultado.falhou = True

        return resultado

    # A string de retorno do despachar() já é a mensagem pronta pra
    # ser falada de volta ao usuário — convenção seguida por todo
    # pacote deste projeto (ver jarvis/servicos/email/remetente.py).
    # Corta uma terceira chamada de rede que existiria se fôssemos
    # mandar o resultado de volta pro modelo narrar.
    resultado.resposta = resultado_despacho
    resultado.usou_ferramenta = True
    resultado.ferramenta_executada = nome_funcao

    return resultado
