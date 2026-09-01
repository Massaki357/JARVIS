# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

import os

load_dotenv()

# Access ID/Client ID do Cloud Project na Tuya IoT Platform.
TUYA_ACCESS_ID = os.getenv(
    "TUYA_ACCESS_ID"
)

# Access Secret/Client Secret do mesmo Cloud Project. Nunca fica
# hardcoded no código — sempre vem do .env.
TUYA_ACCESS_SECRET = os.getenv(
    "TUYA_ACCESS_SECRET"
)

# URL base da API para a Data Center do seu Cloud Project. Confirmado
# ao vivo (não adivinhado): a aba Overview do Cloud Project mostra
# "Data Center: Western America Data Center", que corresponde a
# https://openapi.tuyaus.com — só existe uma America aqui, "Eastern
# America" da dúvida inicial não se aplica a este projeto.
TUYA_API_ENDPOINT = os.getenv(
    "TUYA_API_ENDPOINT"
)

# Categoria de produto usada pela Tuya para hubs de controle
# infravermelho universal ("Universal IR Remote Control").
CATEGORIA_HUB_INFRAVERMELHO = "wnykq"

# DP code padrão usado por interruptores/tomadas Tuya (switches
# simples — mesmo tratamento pros dois). Confirmado ao vivo no painel
# de debug de um dispositivo real (KaBuM! Smart Interruptor
# Inteligente 3, categoria "kg"): switch_1/switch_2/switch_3, Boolean.
# Dispositivos de um canal só usam switch_1.
DP_CODE_SWITCH_PADRAO = "switch_1"

# Duração do cache de dispositivos_tuya.listar_dispositivos(), em
# segundos — evita bater na API da Tuya a cada comando de voz.
DURACAO_CACHE_DISPOSITIVOS_SEGUNDOS = 60


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
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
