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
