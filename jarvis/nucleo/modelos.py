import json

from jarvis.caminhos import CAMINHO_CONFIG_JSON


PADROES = {
    "cerebro": {
        "gemini": {
            "modelo": "gemini-3.1-flash-live-preview",
            "modelo_reserva": "gemini-2.5-flash-native-audio-preview-12-2025",
            "voz": "Charon",
        },
        "openai": {
            "modelo": "gpt-realtime",
            "voz": "marin",
        },
    },
    "subagentes": {
        "agente_ferramentas": "openai/gpt-oss-20b",
        "roteamento_hierarquico": {
            "etapa1": "openai/gpt-oss-20b",
            "etapa2": "openai/gpt-oss-20b",
        },
        "delegacao_ia": {
            "groq": "openai/gpt-oss-20b",
            "cerebras": "gpt-oss-120b",
            "openai": "gpt-4o-mini",
            "gemini": "gemini-3.6-flash",
        },
        "descricao_visual": {
            "gemini": "gemini-3.5-flash-lite",
            "mistral": "mistral-medium-latest",
        },
        "identificacao_visual": {
            "gemini": "gemini-3.5-flash-lite",
            "mistral": "mistral-medium-latest",
        },
        "consolidacao_memoria": "gemini-3.6-flash",
        "localizador_clique": "gemini-3.1-flash-lite",
    },
}

_avisados = set()


def _secao_modelos():
    try:
        dados = json.loads(CAMINHO_CONFIG_JSON.read_text(encoding="utf-8"))

    except (OSError, json.JSONDecodeError):
        return {}

    secao = dados.get("modelos") if isinstance(dados, dict) else None

    return secao if isinstance(secao, dict) else {}


def _buscar(arvore, partes):
    for parte in partes:
        if not isinstance(arvore, dict) or parte not in arvore:
            return None

        arvore = arvore[parte]

    return arvore


def modelo(caminho):
    partes = caminho.split(".")
    padrao = _buscar(PADROES, partes)

    if not isinstance(padrao, str):
        raise KeyError(f"Modelo desconhecido: {caminho}")

    valor = _buscar(_secao_modelos(), partes)

    if isinstance(valor, str) and valor.strip():
        return valor.strip()

    if caminho not in _avisados:
        _avisados.add(caminho)

        print(
            f"Aviso: config.json sem modelos.{caminho} — usando o "
            f"padrão {padrao}."
        )

    return padrao
