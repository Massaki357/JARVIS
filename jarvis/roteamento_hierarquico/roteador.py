import re

from jarvis.nucleo import prompts
from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS
from jarvis.servicos import agentes

from . import catalogo
from . import config
from . import esquema_groq

_PADRAO_MARCADOR = re.compile(
    r"^\s*FERRAMENTAS\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


_POLITICA = agentes.PoliticaRepeticao(
    tentativas_limite=config.TENTATIVAS_RATE_LIMIT,
    tentativas_ferramenta_indevida=config.TENTATIVAS_TOOL_CALL_INDEVIDA,
    espera_base=config.ESPERA_BASE_RATE_LIMIT,
    espera_maxima=config.ESPERA_MAXIMA_RATE_LIMIT,
    rotulo="roteamento_hierarquico",
)


class EtapaExecutada:
    def __init__(self, numero, modelo, usage, latencia_segundos):
        self.numero = numero
        self.modelo = modelo
        self.usage = usage or {}
        self.latencia_segundos = latencia_segundos


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

        # Falha de roteamento nunca pode virar conversa (docs/voz_local.md).
        self.falhou = falhou

        self.etapas = []

    def total_tokens(self):
        return sum(
            etapa.usage.get("total_tokens", 0) for etapa in self.etapas
        )


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


def _consultar(pedido):
    return agentes.executar(pedido, _POLITICA)


def _registrar_etapa(resultado, numero, modelo, resposta):
    resultado.etapas.append(
        EtapaExecutada(
            numero,
            modelo,
            resposta.uso.como_dicionario_provedor(),
            resposta.latencia_segundos,
        )
    )


def _extrair_candidatos_validos(texto_marcador):
    nomes_brutos = [
        nome.strip() for nome in texto_marcador.split(",") if nome.strip()
    ]

    vistos = {}

    for nome in nomes_brutos:
        if nome in catalogo.CATALOGO_CURTO:
            vistos.setdefault(nome, None)

    return list(vistos.keys())[: config.LIMITE_FERRAMENTAS_CANDIDATAS]


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

    pedido_etapa1 = _pedido_groq(
        prompts.ROTEAMENTO_ETAPA1_INSTRUCAO.format(
            catalogo=catalogo.TEXTO_CATALOGO
        ),
        mensagem_usuario,
        config.MODELO_GROQ_ETAPA1,
        historico=historico,
    )

    resposta_etapa1 = _consultar(pedido_etapa1)

    # Plano B: o 400 de tool call indevida acontece com histórico; refaz sem ele.
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
        return resultado

    nomes_candidatos = _extrair_candidatos_validos(marcador.group(1))

    if not nomes_candidatos:
        resultado.resposta = (
            "Entendi que você quer que eu faça algo, mas não "
            "identifiquei qual ação — pode repetir de outro jeito?"
        )
        resultado.pedido_esclarecimento = True

        return resultado

    if len(_categorias_dos_candidatos(nomes_candidatos)) > 1:
        resultado.resposta = _pedido_esclarecimento(nomes_candidatos)
        resultado.pedido_esclarecimento = True

        return resultado

    esquemas = esquema_groq.obter_schemas_completos(
        nomes_candidatos, PACOTES_REGISTRADOS
    )

    if not esquemas:
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
        resultado.resposta = resposta_etapa2.texto

        return resultado

    nome_funcao = chamada.nome
    argumentos = esquema_groq.interpretar_argumentos(chamada.argumentos)

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

    resultado.resposta = resultado_despacho
    resultado.usou_ferramenta = True
    resultado.ferramenta_executada = nome_funcao

    return resultado
