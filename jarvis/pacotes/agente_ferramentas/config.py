from dotenv import load_dotenv

import os

from jarvis.nucleo import modelos

load_dotenv()

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

MODELO = modelos.modelo("subagentes.agente_ferramentas")

TIMEOUT_SEGUNDOS = 12

LIMITE_CANDIDATOS = 3

TENTATIVAS_LIMITE = 3

ESPERA_BASE_SEGUNDOS = 1.0
ESPERA_MAXIMA_SEGUNDOS = 4.0


def _ler_bool(nome, padrao=False):
    bruto = (os.getenv(nome) or "").strip().lower()

    if not bruto:
        return padrao

    return bruto in ("1", "true", "sim", "yes", "on")


def usar_catalogo_completo():
    return _ler_bool("AGENTE_FERRAMENTAS_CATALOGO_COMPLETO", False)


def config_schema():
    return [
        {
            "nome": "AGENTE_FERRAMENTAS_CATALOGO_COMPLETO",
            "rotulo": (
                "Usar as descrições completas no catálogo de busca "
                "(true/false, padrão false — mais preciso, mas "
                "estoura o tier gratuito da Groq)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
