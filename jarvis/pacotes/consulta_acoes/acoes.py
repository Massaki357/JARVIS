from __future__ import annotations

from typing import Any

import requests

from .config import TWELVE_DATA_API_KEY


URL_BASE = "https://api.twelvedata.com"
TIMEOUT_SEGUNDOS = 10

MAXIMO_TICKERS_POR_CHAMADA = 120


def _normalizar_tickers(tickers: list[str]) -> list[str]:
    if not tickers:
        return []

    normalizados: list[str] = []
    vistos: set[str] = set()

    for ticker in tickers:
        ticker_limpo = str(ticker or "").strip().upper()

        if not ticker_limpo or ticker_limpo in vistos:
            continue

        vistos.add(ticker_limpo)
        normalizados.append(ticker_limpo)

    return normalizados


def _para_numero(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _extrair_mensagem_erro(dados: dict[str, Any]) -> str | None:
    if dados.get("status") == "error" or (
        "code" in dados and "message" in dados
    ):
        mensagem = dados.get(
            "message", "Erro desconhecido da Twelve Data."
        )
        codigo = dados.get("code")

        if codigo:
            return f"Erro da Twelve Data ({codigo}): {mensagem}"

        return f"Erro da Twelve Data: {mensagem}"

    return None


def _requisitar(
    endpoint: str,
    parametros: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    if not TWELVE_DATA_API_KEY:
        return {}, "TWELVE_DATA_API_KEY não encontrada no arquivo .env"

    parametros = {**parametros, "apikey": TWELVE_DATA_API_KEY}

    try:
        resposta = requests.get(
            f"{URL_BASE}/{endpoint}",
            params=parametros,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.exceptions.Timeout:
        return (
            {},
            "A consulta à Twelve Data demorou demais e foi interrompida.",
        )
    except requests.exceptions.ConnectionError:
        return (
            {},
            "Não foi possível conectar à Twelve Data. Verifique a internet.",
        )
    except requests.exceptions.RequestException as erro:
        return (
            {},
            f"Falha ao consultar a Twelve Data ({type(erro).__name__}).",
        )

    try:
        dados = resposta.json()
    except ValueError:
        return (
            {},
            f"A Twelve Data retornou uma resposta inválida (HTTP {resposta.status_code}).",
        )

    if not isinstance(dados, dict):
        return {}, "A Twelve Data retornou um formato de resposta inesperado."

    erro_api = _extrair_mensagem_erro(dados)
    if erro_api:
        return {}, erro_api

    if not resposta.ok:
        return (
            {},
            f"A Twelve Data retornou um erro (HTTP {resposta.status_code}).",
        )

    return dados, None


def _resumir_cotacao(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "simbolo": item.get("symbol", ""),
        "preco_atual": _para_numero(item.get("close")),
        "variacao": _para_numero(item.get("change")),
        "variacao_percentual": _para_numero(item.get("percent_change")),
        "volume": _para_numero(item.get("volume")),
        "maxima_dia": _para_numero(item.get("high")),
        "minima_dia": _para_numero(item.get("low")),
    }


def consultar_cotacao(tickers: list[str]) -> dict[str, dict[str, Any]]:
    tickers_validos = _normalizar_tickers(tickers)

    if not tickers_validos:
        return {"erro": "Nenhum ticker válido foi informado."}

    if len(tickers_validos) > MAXIMO_TICKERS_POR_CHAMADA:
        return {
            "erro": (
                "É possível consultar no máximo "
                f"{MAXIMO_TICKERS_POR_CHAMADA} tickers por chamada."
            )
        }

    dados, erro = _requisitar(
        "quote",
        {"symbol": ",".join(tickers_validos)},
    )

    if erro:
        return {"erro": erro}

    if len(tickers_validos) == 1:
        dados = {tickers_validos[0]: dados}

    resultado: dict[str, dict[str, Any]] = {}

    for ticker in tickers_validos:
        item = dados.get(ticker)

        if not isinstance(item, dict):
            resultado[ticker] = {
                "erro": "Símbolo não encontrado na resposta da API."
            }
            continue

        erro_item = _extrair_mensagem_erro(item)
        if erro_item:
            resultado[ticker] = {"erro": erro_item}
            continue

        resultado[ticker] = _resumir_cotacao(item)

    return resultado


def _resumir_candle(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": item.get("datetime", ""),
        "abertura": _para_numero(item.get("open")),
        "maxima": _para_numero(item.get("high")),
        "minima": _para_numero(item.get("low")),
        "fechamento": _para_numero(item.get("close")),
        "volume": _para_numero(item.get("volume")),
    }


def consultar_historico(
    ticker: str,
    intervalo: str = "1day",
    quantidade: int = 30,
) -> list[dict[str, Any]]:
    ticker = str(ticker or "").strip().upper()

    if not ticker:
        return [{"erro": "Nenhum ticker foi informado."}]

    if quantidade <= 0:
        return [{"erro": "A quantidade de candles deve ser maior que zero."}]

    dados, erro = _requisitar(
        "time_series",
        {
            "symbol": ticker,
            "interval": intervalo,
            "outputsize": quantidade,
        },
    )

    if erro:
        return [{"erro": erro}]

    valores = dados.get("values")

    if not isinstance(valores, list):
        return [
            {"erro": "A resposta da API não trouxe candles para este ticker."}
        ]

    candles = [
        _resumir_candle(item)
        for item in valores
        if isinstance(item, dict)
    ]

    candles.reverse()

    return candles


if __name__ == "__main__":
    import json

    print("=== consultar_cotacao(['AAPL', 'MSFT']) ===")
    print(
        json.dumps(
            consultar_cotacao(["AAPL", "MSFT"]),
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== consultar_historico('AAPL', intervalo='1day', quantidade=5) ===")
    print(
        json.dumps(
            consultar_historico("AAPL", intervalo="1day", quantidade=5),
            ensure_ascii=False,
            indent=2,
        )
    )
