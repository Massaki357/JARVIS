import importlib
import os

from dotenv import dotenv_values

from jarvis.caminhos import CAMINHO_ENV

DESCRICOES = {
    "GEMINI_API_KEY": (
        "Chave de API do Gemini",
        "Usada pelo cérebro de voz Gemini. Gere em aistudio.google.com.",
    ),
    "OPENAI_API_KEY": (
        "Chave de API da OpenAI",
        "Usada pelo cérebro de voz OpenAI Realtime. Gere em "
        "platform.openai.com.",
    ),
    "GROQ_API_KEY": (
        "Chave de API da Groq",
        "Usada pelo sub-agente que descobre as ferramentas. Sem ela o "
        "assistente não encontra a maioria das ações. Gere em "
        "console.groq.com.",
    ),
}


def chaves_necessarias():
    from jarvis.nucleo import config

    provedor = config.provedor_ativo()
    chaves = []

    if provedor == "gemini":
        chaves.append("GEMINI_API_KEY")

    elif provedor == "openai":
        chaves.append("OPENAI_API_KEY")

    if provedor == "local" or config.FERRAMENTAS_SOB_DEMANDA:
        chaves.append("GROQ_API_KEY")

    return chaves


def _valor_definido(nome, valores_env):
    return bool(
        str(valores_env.get(nome) or os.environ.get(nome) or "").strip()
    )


def chaves_faltando():
    valores_env = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    return [
        nome
        for nome in chaves_necessarias()
        if not _valor_definido(nome, valores_env)
    ]


# Módulos que guardam a chave numa constante leem na importação: só vale se nenhum foi importado ainda.
def aplicar_no_processo(valores):
    for nome, valor in valores.items():
        os.environ[nome] = valor

    from jarvis.nucleo import config

    importlib.reload(config)
