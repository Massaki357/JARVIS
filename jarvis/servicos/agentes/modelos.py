TIMEOUT_PADRAO_SEGUNDOS = 30

_PROVEDORES = {
    "gemini": {
        "model_provider": "google_genai",
        "parametro_chave": "google_api_key",
        "extras": {},
        # Piso real da API do Gemini: abaixo de 10s volta 400.
        "timeout_minimo": 10,
        "binds": {"automatic_function_calling": {"disable": True}},
        "pacote_pip": "langchain-google-genai",
    },
    "openai": {
        "model_provider": "openai",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-openai",
    },
    "groq": {
        "model_provider": "groq",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-groq",
    },
    # Via ChatOpenAI: langchain-cerebras exige Python <3.13 e rebaixaria o openai.
    "cerebras": {
        "model_provider": "openai",
        "parametro_chave": "api_key",
        "extras": {"base_url": "https://api.cerebras.ai/v1"},
        "pacote_pip": "langchain-openai",
    },
    "mistral": {
        "model_provider": "mistralai",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-mistralai",
    },
}

PROVEDORES_SUPORTADOS = tuple(_PROVEDORES.keys())

_cache = {}


class ProvedorDesconhecido(ValueError):
    pass


class ProvedorIndisponivel(RuntimeError):
    pass


def _identificador_cache(provedor, modelo, temperatura, timeout, api_key):
    return (
        provedor,
        modelo,
        temperatura,
        timeout,
        hash(api_key or ""),
    )


def criar_modelo(
    provedor,
    modelo,
    api_key,
    temperatura=None,
    timeout=None,
):
    definicao = _PROVEDORES.get(provedor)

    if definicao is None:
        raise ProvedorDesconhecido(
            f"Provedor '{provedor}' não é suportado. "
            f"Suportados: {', '.join(PROVEDORES_SUPORTADOS)}."
        )

    if not api_key:
        raise ValueError(
            f"Nenhuma chave de API foi informada para o provedor "
            f"'{provedor}'."
        )

    timeout = timeout or TIMEOUT_PADRAO_SEGUNDOS

    timeout = max(timeout, definicao.get("timeout_minimo", 0))

    identificador = _identificador_cache(
        provedor, modelo, temperatura, timeout, api_key
    )

    if identificador in _cache:
        return _cache[identificador]

    from langchain.chat_models import init_chat_model

    argumentos = {
        "model_provider": definicao["model_provider"],
        definicao["parametro_chave"]: api_key,
        "timeout": timeout,
        # Repetir é política de quem chama (PoliticaRepeticao).
        "max_retries": 0,
        **definicao["extras"],
    }

    if temperatura is not None:
        argumentos["temperature"] = temperatura

    try:
        construido = init_chat_model(modelo, **argumentos)

    except ImportError as erro:
        raise ProvedorIndisponivel(
            f"O pacote de integração do provedor '{provedor}' não está "
            f"instalado. Instale com: pip install "
            f"{definicao['pacote_pip']} ({erro})"
        ) from erro

    _cache[identificador] = construido

    return construido


def argumentos_de_invocacao(provedor):
    definicao = _PROVEDORES.get(provedor) or {}

    return dict(definicao.get("binds") or {})
