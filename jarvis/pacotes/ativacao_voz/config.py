from dotenv import load_dotenv

import os

load_dotenv()

NOME_ATIVACAO = os.getenv(
    "NOME_ATIVACAO",
    "voltar chamada",
)


def config_schema():
    return [
        {
            "nome": "NOME_ATIVACAO",
            "rotulo": (
                "Frase de ativação por voz — inicia uma chamada nova "
                "OU retoma uma chamada pausada (padrão: \"voltar "
                "chamada\" — precisa ser uma palavra/frase real do "
                "vocabulário do modelo Vosk em português; nomes "
                "estrangeiros como o nome do assistente não "
                "funcionam)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
