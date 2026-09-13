from dotenv import dotenv_values, load_dotenv

import os

from jarvis.caminhos import CAMINHO_ENV

load_dotenv()

PROVEDORES_VISAO = ("gemini", "mistral")


def provedor_forcado():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    bruto = valores.get("DESCRICAO_VISUAL_PROVEDOR")

    if bruto is None:
        bruto = os.getenv("DESCRICAO_VISUAL_PROVEDOR")

    valor = (bruto or "").strip().lower()

    if valor in PROVEDORES_VISAO:
        return valor

    return None


# Padrão automático nunca é o mesmo provedor do cérebro ativo.
def provedor_visao():
    forcado = provedor_forcado()

    if forcado:
        return forcado

    from jarvis.nucleo import config as config_nucleo

    if config_nucleo.provedor_ativo() == "gemini":
        return "mistral"

    return "gemini"


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

MODELO_GEMINI = os.getenv(
    "IDENTIFICACAO_VISUAL_MODELO_GEMINI",
    "gemini-3.5-flash-lite",
)

MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY"
)

MODELO_MISTRAL_VISION = os.getenv(
    "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
    "mistral-medium-latest",
)

TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
        "20",
    )
)


def config_schema():
    return [
        {
            "nome": "MISTRAL_API_KEY",
            "rotulo": (
                "Chave de API da Mistral — usada pela segunda opinião "
                "visual sempre que o cérebro de voz ativo for o Gemini "
                "(regra automática: a segunda opinião nunca é o mesmo "
                "cérebro que respondeu), ou quando "
                "DESCRICAO_VISUAL_PROVEDOR=mistral"
            ),
            "sensivel": True,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_MODELO_GEMINI",
            "rotulo": (
                "Modelo de visão do Gemini para a segunda opinião "
                "(padrão: gemini-3.5-flash-lite)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
            "rotulo": "Modelo de visão da Mistral (padrão: mistral-medium-latest)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
            "rotulo": "Tempo limite da chamada, em segundos (padrão: 20)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
