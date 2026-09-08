# Motor de roteamento hierárquico de ferramentas, em duas etapas,
# sobre a API de Chat Completions da Groq (SEM ESTADO — cada
# processar_turno() é uma conversa isolada, sem sessão persistente
# no servidor). Ver jarvis/roteamento_hierarquico/config.py para o
# porquê deste módulo ser standalone e não plugado a nenhum dos dois
# cérebros de voz atuais (Gemini Live / OpenAI Realtime) ainda.
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
import time

import requests

from jarvis.nucleo import prompts
from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS

from . import catalogo
from . import config
from . import esquema_groq

_URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"

# Reconhece "FERRAMENTAS: nome1, nome2" como a ÚNICA linha não vazia
# da resposta da etapa 1 — qualquer outra coisa na resposta é tratada
# como resposta direta do usuário (nunca uma mistura dos dois).
_PADRAO_MARCADOR = re.compile(
    r"^\s*FERRAMENTAS\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
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


# Extrai a explicação REAL de uma resposta de erro da Groq. Sem isto,
# um 429 recuperável (janela de rate limit, reabre em ~1s) fica
# indistinguível de um 500 qualquer: requests só monta "429 Client
# Error: Too Many Requests for url: ...", e o motivo — que vem no
# corpo JSON, incluindo quanto esperar — é descartado.
#
# Foi exatamente essa perda que fez um bug real levar engenharia
# reversa para ser diagnosticado. Nunca volte a ignorar o corpo.
# A Groq recusa com 400 quando o modelo emite uma chamada de
# ferramenta numa requisição que não declarou ferramenta nenhuma:
# "Tool choice is none, but model called a tool".
#
# ISTO NÃO É ERRO DE REQUISIÇÃO NOSSA — é o modelo saindo do combinado.
# A ETAPA 1 manda só texto (o catálogo curto) e espera só texto (a
# linha "FERRAMENTAS: ..."); nenhuma ferramenta é declarada, e é assim
# de propósito, porque declarar os esquemas todos ali é justamente o
# custo que o roteamento em duas etapas existe para evitar. Só que o
# gpt-oss decide, de vez em quando, EXECUTAR a ferramenta em vez de
# escrever o nome dela — e aí a requisição inteira volta 400.
#
# É NÃO DETERMINÍSTICO: medido com a frase e o histórico exatos do
# caso relatado, deu de 1 a 3 falhas em cada 6 chamadas idênticas. E
# depende do HISTÓRICO: sem nenhum turno anterior, 0 em 8; com um turno
# de assistente antes, passa a acontecer. Foi por isso que só apareceu
# depois que as falas do assistente passaram a entrar no histórico.
#
# O QUE NÃO RESOLVE, testado: reforçar o prompt ("você não tem
# ferramentas, nunca emita tool call") não ajudou — 3 falhas em 6
# contra 1 em 6 sem o reforço. O canal de ferramenta do formato
# harmony não se desliga por instrução.
#
# Então o tratamento é repetir: como o resultado varia entre chamadas
# idênticas, uma segunda tentativa quase sempre volta o texto certo.
# É a ÚNICA exceção à regra de não repetir 4xx (repetir um 401 ou um
# 400 de corpo malformado seria gastar o tempo do usuário para receber
# o mesmo erro), e é uma exceção justificada porque aqui a resposta
# não é função só da requisição.
def _e_chamada_de_ferramenta_indevida(detalhe):
    texto = (detalhe or "").lower()

    return "tool" in texto and (
        "tool choice is none" in texto or "called a tool" in texto
    )


def _detalhe_do_erro(resposta):
    try:
        corpo = resposta.json()

    except ValueError:
        texto = (resposta.text or "").strip()

        return texto[:300] if texto else ""

    if isinstance(corpo, dict):
        erro = corpo.get("error")

        if isinstance(erro, dict):
            return str(erro.get("message") or erro)[:300]

        if erro:
            return str(erro)[:300]

    return str(corpo)[:300]


# Quanto esperar antes de repetir, respeitando o retry-after do
# servidor quando ele existe — ninguém adivinha melhor que o próprio
# servidor quando a janela reabre. Sem ele, backoff exponencial.
# Sempre limitado por ESPERA_MAXIMA_RATE_LIMIT, porque o valor vem de
# fora e um número absurdo travaria o turno de voz.
def _espera_do_retry(resposta, tentativa):
    cabecalho = resposta.headers.get("retry-after")

    if cabecalho:
        try:
            return min(
                float(cabecalho),
                config.ESPERA_MAXIMA_RATE_LIMIT,
            )

        except (TypeError, ValueError):
            pass

    return min(
        config.ESPERA_BASE_RATE_LIMIT * (2 ** tentativa),
        config.ESPERA_MAXIMA_RATE_LIMIT,
    )


# Chamada de baixo nível à Groq. Nunca lança — sempre devolve
# (sucesso, dados_ou_mensagem_de_erro, latencia_segundos). "dados" é
# o corpo JSON completo da resposta (não só o texto), porque tanto a
# etapa 1 quanto a etapa 2 precisam de campos diferentes dele
# (conteúdo de texto, tool_calls, usage).
#
# Repete em DOIS casos, cada um com o próprio orçamento: no 429 (o
# servidor diz que a janela reabre) e no 400 específico de "o modelo
# chamou uma ferramenta que ninguém declarou", que é não determinístico
# — ver _e_chamada_de_ferramenta_indevida. Qualquer outro erro volta na
# primeira tentativa: repetir um 401, ou um 400 de corpo malformado, é
# gastar o tempo do usuário para receber o mesmo erro de novo.
def _chamar_groq(mensagens, modelo, tools=None, tool_choice=None):
    corpo = {
        "model": modelo,
        "messages": mensagens,
        "stream": False,
    }

    if tools:
        corpo["tools"] = tools
        corpo["tool_choice"] = tool_choice or "auto"

    inicio = time.monotonic()
    ultimo_erro = "Falha desconhecida ao consultar a Groq."

    # Dois orçamentos de repetição INDEPENDENTES, porque são dois
    # problemas diferentes: o 429 é do servidor e pede espera; o 400 de
    # tool call indevida é do modelo e pede só outra amostragem. Somar
    # os dois num contador só faria um rate limit consumir as
    # tentativas reservadas para o outro caso.
    tentativas_429 = 0
    tentativas_tool = 0

    while True:
        try:
            resposta = requests.post(
                _URL_GROQ,
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=corpo,
                timeout=config.TIMEOUT_SEGUNDOS,
            )

            if resposta.status_code == 429:
                detalhe = _detalhe_do_erro(resposta)
                ultimo_erro = f"Limite de uso da Groq atingido: {detalhe}"

                tentativas_429 += 1

                # Última tentativa: não adianta dormir para desistir
                # logo em seguida.
                if tentativas_429 >= config.TENTATIVAS_RATE_LIMIT:
                    break

                espera = _espera_do_retry(resposta, tentativas_429 - 1)

                print(
                    "[roteamento_hierarquico] Rate limit da Groq "
                    f"(tentativa {tentativas_429}/"
                    f"{config.TENTATIVAS_RATE_LIMIT}); repetindo em "
                    f"{espera:.1f}s. {detalhe}"
                )

                time.sleep(espera)

                continue

            if resposta.status_code >= 400:
                detalhe = _detalhe_do_erro(resposta)

                # A exceção à regra de não repetir 4xx — ver
                # _e_chamada_de_ferramenta_indevida para o porquê.
                if _e_chamada_de_ferramenta_indevida(detalhe):
                    tentativas_tool += 1
                    ultimo_erro = (
                        f"Falha na chamada à Groq ({resposta.status_code})"
                        + (f": {detalhe}" if detalhe else "")
                    )

                    if tentativas_tool < config.TENTATIVAS_TOOL_CALL_INDEVIDA:
                        print(
                            "[roteamento_hierarquico] O modelo tentou chamar "
                            "uma ferramenta numa etapa que não declara "
                            f"nenhuma (tentativa {tentativas_tool}/"
                            f"{config.TENTATIVAS_TOOL_CALL_INDEVIDA}); "
                            "repetindo."
                        )

                        # Sem espera: não é limite de uso, é a
                        # amostragem do modelo. Dormir aqui só atrasaria
                        # a resposta ao usuário.
                        continue

                    return (
                        False,
                        ultimo_erro,
                        time.monotonic() - inicio,
                    )

                return (
                    False,
                    f"Falha na chamada à Groq ({resposta.status_code})"
                    + (f": {detalhe}" if detalhe else ""),
                    time.monotonic() - inicio,
                )

            return True, resposta.json(), time.monotonic() - inicio

        except requests.Timeout:
            return (
                False,
                "Tempo esgotado ao consultar a Groq.",
                time.monotonic() - inicio,
            )

        except requests.RequestException as erro:
            return (
                False,
                f"Falha na chamada à Groq: {erro}",
                time.monotonic() - inicio,
            )

        except ValueError as erro:
            return (
                False,
                f"Resposta inesperada da Groq: {erro}",
                time.monotonic() - inicio,
            )

    return False, ultimo_erro, time.monotonic() - inicio


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
        resultado = ResultadoTurno(
            "GROQ_API_KEY não configurada no .env.",
            falhou=True,
        )

        return resultado

    # --- ETAPA 1: catálogo curto, prefixo fixo ---
    mensagens_etapa1 = [
        {
            "role": "system",
            "content": prompts.ROTEAMENTO_ETAPA1_INSTRUCAO.format(
                catalogo=catalogo.TEXTO_CATALOGO
            ),
        },
        *historico,
        {"role": "user", "content": mensagem_usuario},
    ]

    sucesso, dados, latencia = _chamar_groq(
        mensagens_etapa1, config.MODELO_GROQ_ETAPA1
    )

    # PLANO B, e ele ataca a causa em vez de sortear de novo.
    #
    # O 400 de "o modelo chamou uma ferramenta" acontece muito mais com
    # HISTÓRICO na conversa: medido com a frase do caso relatado, 0 em 8
    # sem nenhum turno anterior, e de 1 a 3 em cada 6 com um turno de
    # assistente antes. As repetições dentro de _chamar_groq reenviam a
    # mesma mensagem e por isso continuam esbarrando no mesmo gatilho —
    # em 5 turnos reais, um esgotou as três.
    #
    # Aqui a última cartada é remover o gatilho: refaz a etapa 1 SEM o
    # histórico. Perde-se contexto (um "e o segundo?" deixa de ser
    # entendido como continuação), e é uma troca que só acontece depois
    # de a chamada normal já ter falhado — perder contexto é muito
    # melhor do que perder o turno inteiro, que é o que o usuário viu.
    if (
        not sucesso
        and historico
        and _e_chamada_de_ferramenta_indevida(str(dados))
    ):
        print(
            "[roteamento_hierarquico] A etapa 1 falhou mesmo repetindo; "
            "tentando sem o histórico da conversa."
        )

        sucesso, dados, latencia = _chamar_groq(
            [mensagens_etapa1[0], mensagens_etapa1[-1]],
            config.MODELO_GROQ_ETAPA1,
        )

    if not sucesso:
        # falhou=True: o roteamento NÃO rodou. Quem chama não pode
        # tratar isto como "era conversa" — o pedido pode muito bem
        # ter sido uma ferramenta.
        return ResultadoTurno(
            f"Não consegui processar seu pedido agora: {dados}",
            falhou=True,
        )

    mensagem_etapa1 = dados["choices"][0]["message"]
    texto_etapa1 = (mensagem_etapa1.get("content") or "").strip()

    resultado = ResultadoTurno(texto_etapa1)
    resultado.etapas.append(
        EtapaExecutada(
            1, config.MODELO_GROQ_ETAPA1, dados.get("usage"), latencia
        )
    )

    marcador = _PADRAO_MARCADOR.match(texto_etapa1)

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
    schemas = esquema_groq.obter_schemas_completos(
        nomes_candidatos, PACOTES_REGISTRADOS
    )

    if not schemas:
        # Os nomes existem no catálogo, mas nenhum pacote registrado
        # os reconheceu de verdade — catálogo desatualizado (ver
        # catalogo.verificar_catalogo_atualizado). Não adivinha.
        resultado.resposta = (
            "Entendi que ação seria, mas não consegui carregar os "
            "detalhes dela agora — pode tentar de novo?"
        )
        resultado.falhou = True

        return resultado

    mensagens_etapa2 = [
        {
            "role": "system",
            "content": prompts.ROTEAMENTO_ETAPA2_INSTRUCAO.format(
                ferramentas=", ".join(nomes_candidatos)
            ),
        },
        *historico,
        {"role": "user", "content": mensagem_usuario},
    ]

    sucesso, dados, latencia = _chamar_groq(
        mensagens_etapa2,
        config.MODELO_GROQ_ETAPA2,
        tools=schemas,
        tool_choice="auto",
    )

    if not sucesso:
        # A etapa 1 JÁ tinha decidido que era ferramenta, então isto é
        # ainda mais claramente uma falha — nunca uma conversa.
        resultado.resposta = (
            f"Não consegui concluir essa ação agora: {dados}"
        )
        resultado.falhou = True

        return resultado

    resultado.etapas.append(
        EtapaExecutada(
            2, config.MODELO_GROQ_ETAPA2, dados.get("usage"), latencia
        )
    )

    mensagem_etapa2 = dados["choices"][0]["message"]
    chamadas = mensagem_etapa2.get("tool_calls") or []

    if not chamadas:
        # O modelo, já vendo os detalhes completos, decidiu que
        # nenhuma ferramenta realmente serve — o texto dele vira a
        # resposta final, mesmo tratamento da etapa 1.
        resultado.resposta = (mensagem_etapa2.get("content") or "").strip()

        return resultado

    # No máximo UMA chamada por turno — mesma suposição de "uma ação
    # por pedido" já usada em todo o projeto (ex.: clicar_elemento_
    # visual). Se o modelo devolver mais de uma, só a primeira roda.
    primeira_chamada = chamadas[0]["function"]
    nome_funcao = primeira_chamada["name"]
    argumentos = esquema_groq.interpretar_argumentos(
        primeira_chamada.get("arguments")
    )

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
