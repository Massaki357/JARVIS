from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import catalogo
from . import config
from . import instrucoes
from . import manual

_ESQUEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "ferramentas": {
            "type": "array",
            "items": {"type": "string"},
        },
        "motivo": {"type": "string"},
    },
    "required": ["ferramentas", "motivo"],
}

_POLITICA = agentes.PoliticaRepeticao(
    tentativas_limite=config.TENTATIVAS_LIMITE,
    espera_base=config.ESPERA_BASE_SEGUNDOS,
    espera_maxima=config.ESPERA_MAXIMA_SEGUNDOS,
    rotulo="agente_ferramentas",
)


# Todo nome devolvido pelo modelo é conferido contra o catálogo real.
def _nomes_validos(dados, itens):
    brutos = (dados or {}).get("ferramentas")

    if not isinstance(brutos, list):
        return []

    vistos = []

    for bruto in brutos:
        if not isinstance(bruto, str):
            continue

        nome = bruto.strip()

        if not nome or nome in vistos:
            continue

        if catalogo.procurar(itens, nome) is None:
            print(
                "[agente_ferramentas] O sub-agente citou uma "
                f"ferramenta que não existe no catálogo: {nome!r} "
                "(descartada)."
            )

            continue

        vistos.append(nome)

    return vistos[: config.LIMITE_CANDIDATOS]


def buscar(pedido):
    pedido = " ".join(str(pedido or "").split())

    if not pedido:
        return instrucoes.falha(
            "nenhuma descrição do que o usuário quer foi informada"
        )

    if not config.GROQ_API_KEY:
        return instrucoes.falha("GROQ_API_KEY não configurada no .env")

    try:
        itens = catalogo.montar()

    except Exception as erro:
        return instrucoes.falha(
            f"o catálogo de ferramentas não carregou ({erro})"
        )

    if not itens:
        return instrucoes.falha(
            "o catálogo de ferramentas voltou vazio"
        )

    texto_catalogo = catalogo.texto_para_prompt(
        itens,
        usar_descricao_completa=config.usar_catalogo_completo(),
    )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="groq",
            modelo=config.MODELO,
            api_key=config.GROQ_API_KEY,
            instrucao_sistema=prompts.AGENTE_FERRAMENTAS_BUSCA.format(
                catalogo=texto_catalogo,
                limite=config.LIMITE_CANDIDATOS,
            ),
            texto=pedido,
            esquema_resposta=_ESQUEMA_RESPOSTA,
            timeout=config.TIMEOUT_SEGUNDOS,
        ),
        _POLITICA,
    )

    if not resposta.sucesso:
        print(
            f"[agente_ferramentas] Falha ao consultar o sub-agente: "
            f"{resposta.erro}"
        )

        return instrucoes.falha(resposta.erro)

    nomes = _nomes_validos(resposta.dados, itens)
    motivo = " ".join(
        str((resposta.dados or {}).get("motivo") or "").split()
    )

    if not nomes:
        return instrucoes.nenhuma_ferramenta(motivo)

    recomendada = catalogo.procurar(itens, nomes[0])
    alternativas = [
        catalogo.procurar(itens, nome) for nome in nomes[1:]
    ]

    return instrucoes.montar(
        recomendada,
        [item for item in alternativas if item],
        motivo,
        manual=manual.secao_de(recomendada["nome"]),
    )
