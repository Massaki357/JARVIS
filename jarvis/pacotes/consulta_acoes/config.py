# Configuração do pacote de consulta de ações (Twelve Data) — cada
# pacote isolado faz sua própria load_dotenv() (mesmo padrão de
# rede_jarvis/casa_inteligente/criar_arquivo), sem depender de
# jarvis/nucleo/config.py.
#
# No JARVIS COMPLETO esta chave morava em core/config.py e só era
# usada pelo provedor OpenAI Realtime. Aqui ela pertence ao pacote, e
# o pacote funciona igual nos dois cérebros de voz (Gemini Live e
# OpenAI Realtime), porque os dois montam suas ferramentas a partir de
# PACOTES_REGISTRADOS.
import os

from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")


def config_schema():
    return [
        {
            "nome": "TWELVE_DATA_API_KEY",
            "rotulo": (
                "Chave da API da Twelve Data (cotação e histórico "
                "de ações)"
            ),
            "sensivel": True,
            "obrigatoria": False,
        },
    ]
