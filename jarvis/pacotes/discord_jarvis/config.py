from dotenv import load_dotenv

import os

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv(
    "DISCORD_BOT_TOKEN"
)

TIMEOUT_CONEXAO_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_CONEXAO",
        "15",
    )
)

TIMEOUT_OPERACAO_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_OPERACAO",
        "15",
    )
)

TIMEOUT_LISTAGEM_MEMBROS_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_LISTAGEM_MEMBROS",
        "30",
    )
)


def config_schema():
    return [
        {
            "nome": "DISCORD_BOT_TOKEN",
            "rotulo": "Token do bot do Discord",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "DISCORD_TIMEOUT_CONEXAO",
            "rotulo": "Tempo limite de conexão, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DISCORD_TIMEOUT_OPERACAO",
            "rotulo": "Tempo limite por operação, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DISCORD_TIMEOUT_LISTAGEM_MEMBROS",
            "rotulo": "Tempo limite pra listar membros, em segundos (padrão: 30)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
