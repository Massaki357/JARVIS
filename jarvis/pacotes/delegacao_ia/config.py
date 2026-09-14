from dotenv import load_dotenv

import os

from jarvis.nucleo import modelos

load_dotenv()

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

CEREBRAS_API_KEY = os.getenv(
    "CEREBRAS_API_KEY"
)

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

TIMEOUT_SEGUNDOS = 8

MODELO_GROQ = modelos.modelo("subagentes.delegacao_ia.groq")

MODELO_CEREBRAS = modelos.modelo("subagentes.delegacao_ia.cerebras")

MODELO_OPENAI = modelos.modelo("subagentes.delegacao_ia.openai")

MODELO_GEMINI = modelos.modelo("subagentes.delegacao_ia.gemini")

TIMEOUT_LONGO_SEGUNDOS = 60


def config_schema():
    return [
        {
            "nome": "GROQ_API_KEY",
            "rotulo": "Chave de API da Groq",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "CEREBRAS_API_KEY",
            "rotulo": "Chave de API da Cerebras",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "OPENAI_API_KEY",
            "rotulo": "Chave de API da OpenAI (segunda_opiniao)",
            "sensivel": True,
            "obrigatoria": True,
        },
    ]
