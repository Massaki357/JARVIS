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
    ):
        self.resposta = resposta
        self.usou_ferramenta = usou_ferramenta
        self.ferramenta_executada = ferramenta_executada
        self.pedido_esclarecimento = pedido_esclarecimento
        self.etapas = []

    def total_tokens(self):
        return sum(
            etapa.usage.get("total_tokens", 0) for etapa in self.etapas
        )


# Chamada de baixo nível à Groq. Nunca lança — sempre devolve
# (sucesso, dados_ou_mensagem_de_erro, latencia_segundos). "dados" é
# o corpo JSON completo da resposta (não só o texto), porque tanto a
# etapa 1 quanto a etapa 2 precisam de campos diferentes dele
# (conteúdo de texto, tool_calls, usage).
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

        resposta.raise_for_status()

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
# PACOTES_REGISTRADOS que jarvis/gemini/cliente_live.py já usa —
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
def processar_turno(mensagem_usuario, historico=None):
    historico = historico or []

    if not config.GROQ_API_KEY:
        resultado = ResultadoTurno(
            "GROQ_API_KEY não configurada no .env."
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

    if not sucesso:
        return ResultadoTurno(
            f"Não consegui processar seu pedido agora: {dados}"
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
        resultado.resposta = (
            f"Não consegui concluir essa ação agora: {dados}"
        )

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

    resultado_despacho = _despachar(nome_funcao, argumentos)

    if resultado_despacho is None:
        resultado.resposta = (
            f"A ferramenta '{nome_funcao}' não foi reconhecida por "
            "nenhum pacote registrado."
        )

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
