from dotenv import load_dotenv

import os

from jarvis.nucleo import modelos

load_dotenv()

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

TIMEOUT_SEGUNDOS = 8

MODELO_GROQ_ETAPA1 = modelos.modelo("subagentes.roteamento_hierarquico.etapa1")

MODELO_GROQ_ETAPA2 = modelos.modelo("subagentes.roteamento_hierarquico.etapa2")

TENTATIVAS_RATE_LIMIT = 3

TENTATIVAS_TOOL_CALL_INDEVIDA = 2

ESPERA_BASE_RATE_LIMIT = 1.0

ESPERA_MAXIMA_RATE_LIMIT = 5.0

LIMITE_FERRAMENTAS_CANDIDATAS = 3

