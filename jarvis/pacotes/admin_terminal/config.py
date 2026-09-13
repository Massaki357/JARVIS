from dotenv import load_dotenv

import os
from pathlib import Path

from jarvis.caminhos import PASTA_DADOS, PASTA_LOGS, garantir_pasta

load_dotenv()

NOME_TAREFA_AGENDADA = os.getenv(
    "ADMIN_TERMINAL_NOME_TAREFA",
    "JarvisAdminTerminal",
)

TIMEOUT_PADRAO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_PADRAO",
        "30",
    )
)

TIMEOUT_COMANDO_LONGO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_LONGO",
        "300",
    )
)

TIMEOUT_CONFIRMACAO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_CONFIRMACAO",
        "40",
    )
)

MARGEM_ESPERA_TAREFA_SEGUNDOS = 10

PASTA_PACOTE = Path(__file__).resolve().parent

PASTA_FILA = garantir_pasta(PASTA_DADOS) / "admin_fila"

ARQUIVO_LOG = garantir_pasta(PASTA_LOGS) / "comandos_admin.log"

LIMITE_TAMANHO_LOG_BYTES = 5 * 1024 * 1024

ARQUIVO_WHITELIST = PASTA_PACOTE / "whitelist.json"


def config_schema():
    return [
        {
            "nome": "ADMIN_TERMINAL_NOME_TAREFA",
            "rotulo": "Nome da Tarefa Agendada (padrão: JarvisAdminTerminal)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_PADRAO",
            "rotulo": "Tempo limite padrão por comando, em segundos (padrão: 30)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_LONGO",
            "rotulo": "Tempo limite para comandos de execução longa, em segundos (padrão: 300)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_CONFIRMACAO",
            "rotulo": "Tempo limite para confirmar um comando, em segundos (padrão: 40)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
