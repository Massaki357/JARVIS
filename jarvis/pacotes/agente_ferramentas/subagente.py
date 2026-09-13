"""
O sub-agente: uma consulta à Groq que lê o catálogo e diz QUAL
ferramenta atende ao pedido do cérebro.

Ele não executa nada. Quem executa continua sendo o cérebro, com a
própria chamada de função — este pacote só devolve a recomendação e
as instruções. Essa separação é o ponto: executar aqui significaria
um segundo lugar do projeto despachando ferramentas (o roteamento
hierárquico já é um), com as travas de segurança de cada tool
dependendo de qual caminho chamou.

FORMATO DA RESPOSTA: modo JSON do provedor (response_format),
confirmado ao vivo no openai/gpt-oss-20b antes de este código ser
escrito. Mas o modo JSON garante SINTAXE, nunca CONTEÚDO: nenhum
provedor promete que um nome citado lá dentro existe neste projeto,
então todo nome que volta é conferido contra o catálogo real. Um nome
inventado é descartado em silêncio, nunca repassado ao cérebro.
"""

from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import catalogo
from . import config
from . import instrucoes
from . import manual

# Esquema da resposta, exigido do provedor. O sub-agente só pode
# devolver estas duas chaves — nada de texto solto em volta, nada de
# campos extras que ninguém vai ler.
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


def _nomes_validos(dados, itens):
    """
    Os nomes devolvidos pelo sub-agente que existem DE VERDADE no
    catálogo, na ordem em que ele os citou, sem duplicatas e cortados
    no limite configurado.

    Mesma disciplina do roteamento hierárquico: o modelo aponta, o
    código confere. Um nome que não existe some aqui.
    """
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
    """
    Recebe o pedido em linguagem natural que o CÉREBRO escreveu (ex.:
    "o usuário pediu para verificar a tela dele") e devolve a string
    pronta para voltar como resultado da tool.

    Nunca levanta exceção: toda saída é um dos três textos de
    instrucoes.py — recomendação, nenhuma ferramenta, ou falha.
    """
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
        # Duas situações caem aqui e as duas terminam igual: o
        # sub-agente disse honestamente que nada serve, ou citou só
        # nomes inexistentes. Nos dois casos não há ferramenta para
        # recomendar, e adivinhar uma seria pior do que admitir.
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
