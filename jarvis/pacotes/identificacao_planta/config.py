from dotenv import load_dotenv

import os

load_dotenv()

PLANTNET_API_KEY = os.getenv(
    "PLANTNET_API_KEY"
)

PROJETO_PLANTNET = os.getenv(
    "PLANTNET_PROJETO",
    "all",
)

TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "PLANTNET_TIMEOUT_SEGUNDOS",
        "15",
    )
)

QUANTIDADE_RESULTADOS = 3


def config_schema():
    return [
        {
            "nome": "PLANTNET_API_KEY",
            "rotulo": "Chave de API do Pl@ntNet (my.plantnet.org)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "PLANTNET_PROJETO",
            "rotulo": "Flora/projeto de busca (padrão: all)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PLANTNET_TIMEOUT_SEGUNDOS",
            "rotulo": "Tempo limite da chamada, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
