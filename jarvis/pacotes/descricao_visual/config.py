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


def provedor_visao():
    return provedor_forcado() or "gemini"


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

MODELO_GEMINI = os.getenv(
    "DESCRICAO_VISUAL_MODELO_GEMINI",
    "gemini-3.5-flash-lite",
)

MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY"
)

MODELO_MISTRAL = os.getenv(
    "DESCRICAO_VISUAL_MODELO_MISTRAL",
    "mistral-medium-latest",
)

TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "DESCRICAO_VISUAL_TIMEOUT_SEGUNDOS",
        "30",
    )
)


def config_schema():
    return [
        {
            "nome": "DESCRICAO_VISUAL_PROVEDOR",
            "rotulo": (
                "Provedor de visão (vale para descrever tela/câmera e "
                "para a segunda opinião visual). Em branco: descrever "
                "usa o Gemini, e a segunda opinião usa automaticamente "
                "o provedor oposto ao cérebro de voz ativo"
            ),
            "sensivel": False,
            "obrigatoria": False,
            "opcoes": [
                ("", "Automático (recomendado)"),
                ("gemini", "Forçar Gemini"),
                ("mistral", "Forçar Mistral"),
            ],
        },
        {
            "nome": "DESCRICAO_VISUAL_MODELO_GEMINI",
            "rotulo": (
                "Modelo de visão do Gemini "
                "(padrão: gemini-3.5-flash-lite)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DESCRICAO_VISUAL_MODELO_MISTRAL",
            "rotulo": (
                "Modelo de visão da Mistral "
                "(padrão: mistral-medium-latest)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DESCRICAO_VISUAL_TIMEOUT_SEGUNDOS",
            "rotulo": (
                "Tempo limite da chamada de visão, em segundos "
                "(padrão: 30 — vale para os dois provedores)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
