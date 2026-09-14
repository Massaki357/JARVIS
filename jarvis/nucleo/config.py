import os
from dotenv import dotenv_values, load_dotenv

from jarvis.caminhos import CAMINHO_ENV
from jarvis.nucleo import modelos

load_dotenv()

PROVEDOR_IA = os.getenv("PROVEDOR_IA", "gemini").strip().lower()


# Única lista de cérebros de voz: nunca copiar (docs/nucleo-core.md).
OPCOES_PROVEDOR = (
    ("gemini", "Gemini"),
    ("openai", "OpenAI"),
    ("local", "Servidor local (alfred-server)"),
)

PROVEDORES_VALIDOS = tuple(valor for valor, _ in OPCOES_PROVEDOR)


def provedor_ativo():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    valor = (valores.get("PROVEDOR_IA") or "gemini").strip().lower()

    if valor in PROVEDORES_VALIDOS:
        return valor

    return "gemini"


def usar_provedor_openai():
    return provedor_ativo() == "openai"


def usar_provedor_local():
    return provedor_ativo() == "local"


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

NOME_JARVIS = (os.getenv("NOME_JARVIS", "ALFRED").strip() or "ALFRED")


def obter_nome_jarvis():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    return (valores.get("NOME_JARVIS") or "ALFRED").strip() or "ALFRED"

# Padrão True; esta variável é a única forma sancionada de desligar (CLAUDE.md).
EXIGIR_AUTENTICACAO = os.getenv(
    "EXIGIR_AUTENTICACAO",
    "true",
).strip().lower() not in ("false", "0", "nao", "não")

FERRAMENTAS_SOB_DEMANDA = os.getenv(
    "FERRAMENTAS_SOB_DEMANDA",
    "true",
).strip().lower() not in ("false", "0", "nao", "não")

TIMEOUT_INATIVIDADE_SEGUNDOS = int(
    os.getenv(
        "TIMEOUT_INATIVIDADE_SEGUNDOS",
        "300",
    )
)


def config_schema():
    return [
        {
            "nome": "GEMINI_API_KEY",
            "rotulo": "Chave da API do Gemini (obrigatória para o app funcionar)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "NOME_JARVIS",
            "rotulo": (
                "Nome de identidade do assistente (padrão: ALFRED — "
                "vale já na próxima chamada; também editável direto "
                "na tela principal)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "FERRAMENTAS_SOB_DEMANDA",
            "rotulo": (
                "Descobrir ferramentas sob demanda em vez de declarar "
                "todas (true/false, padrão true — economiza mais da "
                "metade dos tokens de cada turno)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EXIGIR_AUTENTICACAO",
            "rotulo": (
                "Exigir a palavra-chave de autenticação por voz "
                "(padrão: true — nunca desative sem entender o risco)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PROVEDOR_IA",
            "rotulo": (
                "Cérebro de voz ativo (vale já na próxima chamada, "
                "sem precisar reiniciar o app)"
            ),
            "sensivel": False,
            "obrigatoria": False,
            "opcoes": list(OPCOES_PROVEDOR),
        },
        {
            "nome": "TIMEOUT_INATIVIDADE_SEGUNDOS",
            "rotulo": (
                "Tempo sem atividade real antes de encerrar a "
                "chamada sozinho, em segundos (padrão: 300)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]

GEMINI_LIVE_MODEL = modelos.modelo("cerebro.gemini.modelo")

GEMINI_LIVE_MODEL_FALLBACK = modelos.modelo("cerebro.gemini.modelo_reserva")


GEMINI_VOICE = modelos.modelo("cerebro.gemini.voz")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_REALTIME_MODEL = modelos.modelo("cerebro.openai.modelo")


OPENAI_VOICE = modelos.modelo("cerebro.openai.voz")
