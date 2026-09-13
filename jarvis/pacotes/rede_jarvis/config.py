from dotenv import load_dotenv

import os
from pathlib import Path

from jarvis.caminhos import PASTA_LOGS, garantir_pasta

load_dotenv()

MQTT_HOST = os.getenv(
    "MQTT_HOST"
)

MQTT_PORT = int(
    os.getenv(
        "MQTT_PORT",
        "8883",
    )
)

MQTT_USERNAME = os.getenv(
    "MQTT_USERNAME"
)

MQTT_PASSWORD = os.getenv(
    "MQTT_PASSWORD"
)

TOKEN_REDE_JARVIS = os.getenv(
    "TOKEN_REDE_JARVIS"
)

NOME_MAQUINA = os.getenv(
    "NOME_MAQUINA",
    "maquina-sem-nome",
)

PASTA_TRANSFERENCIAS_PADRAO = Path(
    os.getenv(
        "PASTA_TRANSFERENCIAS_PADRAO",
        str(Path.home() / "Downloads" / "JarvisRecebidos"),
    )
)

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON"
)

PEDIR_PERMISSAO = (
    os.getenv(
        "PEDIR_PERMISSAO",
        "true",
    ).strip().lower()
    == "true"
)

# Comandos remotos só por whitelist, nunca comando ou caminho vindo do MQTT.
WHITELIST_APPS = {
    "bloco de notas": "notepad.exe",
    "calculadora": "calc.exe",
    "explorador de arquivos": "explorer.exe",
    "paint": "mspaint.exe",
}

PASTAS_PERMITIDAS_BUSCA = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]

LIMITE_RESULTADOS_BUSCA = 15

INTERVALO_VISUALIZACAO_REMOTA = 2.5

TIMEOUT_VISUALIZACAO_REMOTA = 90

LIMITE_MQTT_MB = 4.5

TIMEOUT_TRANSFERENCIA_ARQUIVO = 60

TIMEOUT_PERMISSAO = 40

TIMEOUT_RESPOSTA_COMANDO = 15

TIMEOUT_CONSULTA_SERVICE_ACCOUNT = 15

ARQUIVO_LOG = (
    garantir_pasta(PASTA_LOGS) / "comandos_remotos.log"
)

LIMITE_TAMANHO_LOG_BYTES = 5 * 1024 * 1024


def config_schema():
    return [
        {
            "nome": "MQTT_HOST",
            "rotulo": "Host do broker MQTT",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "MQTT_PORT",
            "rotulo": "Porta do broker MQTT",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MQTT_USERNAME",
            "rotulo": "Usuário do broker MQTT",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "MQTT_PASSWORD",
            "rotulo": "Senha do broker MQTT",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "TOKEN_REDE_JARVIS",
            "rotulo": "Token compartilhado entre as máquinas",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "NOME_MAQUINA",
            "rotulo": "Nome desta máquina",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PASTA_TRANSFERENCIAS_PADRAO",
            "rotulo": "Pasta padrão para arquivos recebidos",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "GOOGLE_SERVICE_ACCOUNT_JSON",
            "rotulo": "Caminho da credencial do Google Drive (arquivos grandes)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PEDIR_PERMISSAO",
            "rotulo": "Pedir permissão antes de executar comando remoto (true/false)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
