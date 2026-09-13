from dotenv import load_dotenv

import os

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

MODELO_GROQ = os.getenv(
    "DELEGACAO_MODELO_GROQ",
    "openai/gpt-oss-20b",
)

MODELO_CEREBRAS = os.getenv(
    "DELEGACAO_MODELO_CEREBRAS",
    "gpt-oss-120b",
)

MODELO_OPENAI = os.getenv(
    "DELEGACAO_MODELO_OPENAI",
    "gpt-4o-mini",
)

MODELO_GEMINI = os.getenv(
    "DELEGACAO_MODELO_GEMINI",
    "gemini-3.6-flash",
)

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
        {
            "nome": "DELEGACAO_MODELO_GROQ",
            "rotulo": "Modelo usado na Groq (padrão: openai/gpt-oss-20b)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DELEGACAO_MODELO_CEREBRAS",
            "rotulo": "Modelo usado na Cerebras (padrão: gpt-oss-120b)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DELEGACAO_MODELO_OPENAI",
            "rotulo": "Modelo usado na OpenAI (padrão: gpt-4o-mini)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DELEGACAO_MODELO_GEMINI",
            "rotulo": "Modelo do Gemini (delegação e criação de perfil)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
