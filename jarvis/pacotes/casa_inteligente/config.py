from dotenv import load_dotenv

import os

load_dotenv()

TUYA_ACCESS_ID = os.getenv(
    "TUYA_ACCESS_ID"
)

TUYA_ACCESS_SECRET = os.getenv(
    "TUYA_ACCESS_SECRET"
)

TUYA_API_ENDPOINT = os.getenv(
    "TUYA_API_ENDPOINT"
)

CATEGORIA_HUB_INFRAVERMELHO = "wnykq"

DP_CODE_SWITCH_PADRAO = "switch_1"

DURACAO_CACHE_DISPOSITIVOS_SEGUNDOS = 60


def config_schema():
    return [
        {
            "nome": "TUYA_ACCESS_ID",
            "rotulo": "Access ID / Client ID (Tuya IoT Platform)",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "TUYA_ACCESS_SECRET",
            "rotulo": "Access Secret / Client Secret (Tuya IoT Platform)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "TUYA_API_ENDPOINT",
            "rotulo": "Endpoint da API (Data Center do Cloud Project)",
            "sensivel": False,
            "obrigatoria": True,
        },
    ]
