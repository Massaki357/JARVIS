# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

import os

load_dotenv()

# Chaves de API dos provedores de LLM usados pra delegação de
# tarefas de texto. Já existiam no .env antes deste pacote (usadas
# por outras ferramentas do curso) — aqui só são lidas, nunca ficam
# hardcoded no código.
GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

CEREBRAS_API_KEY = os.getenv(
    "CEREBRAS_API_KEY"
)

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

# Timeout de cada chamada de completions, em segundos. Curto de
# propósito: se um provedor demorar mais que isso, desiste e tenta o
# fallback (ou devolve o controle pro Jarvis) em vez de travar a
# resposta por voz esperando.
TIMEOUT_SEGUNDOS = 8

# Modelos usados em cada provedor. Cada um é sobrescrevível por
# variável de ambiente (útil se um modelo for descontinuado sem
# precisar editar código) — confirmados ao vivo consultando
# GET /v1/models de cada provedor com a chave real, não adivinhados
# (o catálogo muda com frequência e nomes antigos somem).
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


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# INTEGRATION.md, seção "Tela de configurações".
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
    ]
