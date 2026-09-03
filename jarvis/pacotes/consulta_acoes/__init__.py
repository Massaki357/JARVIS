"""
Cotação atual e histórico de preços de ações (Twelve Data).

Trazido do JARVIS COMPLETO (actions/consulta_acoes_action.py) e
reembalado no contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md. Lá ele só existia para o provedor OpenAI
Realtime; aqui é um pacote normal, então funciona igual nos dois
cérebros de voz (Gemini Live e OpenAI Realtime), sem nenhuma fiação
extra.

acoes.py devolve estruturas Python (dict/list) porque foi escrito
para ser serializado direto no output de uma tool da OpenAI. O
contrato deste projeto exige que despachar() devolva uma STRING
pronta para o modelo falar, então a formatação para texto acontece
aqui, e não lá — assim acoes.py continua idêntico ao original.
"""

# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import acoes

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="consultar_cotacao_acao",
        description=(
            "Consulta a cotação atual em tempo real de uma ou mais "
            "ações (preço, variação absoluta, variação percentual, "
            "volume, máxima e mínima do dia). Use sempre que o "
            "usuário perguntar o preço, a cotação ou como está uma "
            "ação agora. Pode consultar vários tickers de uma vez, "
            "por exemplo ao comparar duas empresas."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tickers": types.Schema(
                    type="ARRAY",
                    items=types.Schema(type="STRING"),
                    description=(
                        "Lista de tickers a consultar, por exemplo "
                        "['AAPL', 'MSFT']. Use o ticker da bolsa, não "
                        "o nome comercial da empresa."
                    ),
                ),
            },
            required=["tickers"],
        ),
    ),

    types.FunctionDeclaration(
        name="consultar_historico_acao",
        description=(
            "Consulta o histórico recente de preços (candles) de uma "
            "ação específica. Use antes de opinar se uma ação tende a "
            "subir ou cair, para basear a análise na tendência recente "
            "de preço, e não apenas na cotação do momento."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "ticker": types.Schema(
                    type="STRING",
                    description="Ticker da ação, por exemplo 'AAPL'.",
                ),
                "intervalo": types.Schema(
                    type="STRING",
                    description=(
                        "Intervalo de cada candle: '1day', '1week', "
                        "'1min', etc. Use '1day' como padrão."
                    ),
                ),
                "quantidade": types.Schema(
                    type="INTEGER",
                    description=(
                        "Quantidade de candles mais recentes a "
                        "retornar. Use 30 como padrão."
                    ),
                ),
            },
            required=["ticker"],
        ),
    ),
]

# Quantos candles do histórico entram no texto devolvido ao modelo.
# O parâmetro quantidade da tool continua valendo para a consulta em
# si (a tendência é calculada sobre o período inteiro); este limite
# existe só para não despejar 30 linhas de candle no contexto de uma
# conversa falada.
MAXIMO_CANDLES_NO_TEXTO = 8


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def _numero(valor, casas=2):
    if valor is None:
        return "indisponível"

    return f"{valor:,.{casas}f}".replace(",", "X").replace(
        ".", ","
    ).replace("X", ".")


def _texto_cotacao(resultado):
    # Falha geral (sem chave, rede fora, limite de requisições) vem
    # como {"erro": "..."} — ver consultar_cotacao em acoes.py.
    if "erro" in resultado and len(resultado) == 1:
        return resultado["erro"]

    linhas = []

    for ticker, dados in resultado.items():
        if "erro" in dados:
            linhas.append(f"{ticker}: {dados['erro']}")
            continue

        linhas.append(
            f"{ticker}: preço {_numero(dados.get('preco_atual'))}, "
            f"variação {_numero(dados.get('variacao'))} "
            f"({_numero(dados.get('variacao_percentual'))}%), "
            f"máxima do dia {_numero(dados.get('maxima_dia'))}, "
            f"mínima do dia {_numero(dados.get('minima_dia'))}, "
            f"volume {_numero(dados.get('volume'), 0)}"
        )

    if not linhas:
        return "A consulta não retornou nenhuma cotação."

    return "Cotação atual — " + " | ".join(linhas)


def _texto_historico(ticker, intervalo, candles):
    # Falha vem como [{"erro": "..."}] — ver consultar_historico.
    if len(candles) == 1 and "erro" in candles[0]:
        return candles[0]["erro"]

    if not candles:
        return (
            f"Não encontrei histórico de preços para {ticker}."
        )

    primeiro = candles[0]
    ultimo = candles[-1]

    fechamento_inicial = primeiro.get("fechamento")
    fechamento_final = ultimo.get("fechamento")

    # Tendência do período INTEIRO consultado, não só dos candles que
    # entram no texto abaixo — é justamente o que a tool existe para
    # embasar.
    if fechamento_inicial and fechamento_final:
        variacao = (
            (fechamento_final - fechamento_inicial)
            / fechamento_inicial
        ) * 100

        tendencia = (
            f"No período consultado ({len(candles)} candles de "
            f"{intervalo}, de {primeiro.get('data', '?')} a "
            f"{ultimo.get('data', '?')}), o fechamento saiu de "
            f"{_numero(fechamento_inicial)} para "
            f"{_numero(fechamento_final)}, ou seja "
            f"{_numero(variacao)}%. "
        )

    else:
        tendencia = ""

    recentes = candles[-MAXIMO_CANDLES_NO_TEXTO:]

    detalhe = " | ".join(
        f"{candle.get('data', '?')}: abertura "
        f"{_numero(candle.get('abertura'))}, máxima "
        f"{_numero(candle.get('maxima'))}, mínima "
        f"{_numero(candle.get('minima'))}, fechamento "
        f"{_numero(candle.get('fechamento'))}"
        for candle in recentes
    )

    return (
        f"Histórico de {ticker}. {tendencia}"
        f"Candles mais recentes — {detalhe}"
    )


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "consultar_cotacao_acao":
        tickers = argumentos.get("tickers") or []

        # O modelo às vezes manda um ticker solto em vez de lista.
        if isinstance(tickers, str):
            tickers = [tickers]

        return _texto_cotacao(
            acoes.consultar_cotacao(list(tickers))
        )

    if nome_funcao == "consultar_historico_acao":
        ticker = argumentos.get("ticker", "")
        intervalo = argumentos.get("intervalo") or "1day"

        try:
            quantidade = int(argumentos.get("quantidade") or 30)

        except (TypeError, ValueError):
            quantidade = 30

        return _texto_historico(
            str(ticker or "").strip().upper(),
            intervalo,
            acoes.consultar_historico(
                ticker,
                intervalo,
                quantidade,
            ),
        )

    return None
