from dotenv import load_dotenv

import os

load_dotenv()

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

TIMEOUT_SEGUNDOS = 8

MODELO_GROQ_ETAPA1 = os.getenv(
    "ROTEAMENTO_MODELO_GROQ_ETAPA1",
    "openai/gpt-oss-20b",
)

MODELO_GROQ_ETAPA2 = os.getenv(
    "ROTEAMENTO_MODELO_GROQ_ETAPA2",
    "openai/gpt-oss-20b",
)

TENTATIVAS_RATE_LIMIT = 3

TENTATIVAS_TOOL_CALL_INDEVIDA = 2

ESPERA_BASE_RATE_LIMIT = 1.0

ESPERA_MAXIMA_RATE_LIMIT = 5.0

LIMITE_FERRAMENTAS_CANDIDATAS = 3


def config_schema():
    return [
        {
            "nome": "ROTEAMENTO_MODELO_GROQ_ETAPA1",
            "rotulo": (
                "Modelo da etapa 1 — catálogo curto (padrão: "
                "openai/gpt-oss-20b)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ROTEAMENTO_MODELO_GROQ_ETAPA2",
            "rotulo": (
                "Modelo da etapa 2 — schema completo (padrão: "
                "openai/gpt-oss-20b, precisa suportar tool-calling)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
