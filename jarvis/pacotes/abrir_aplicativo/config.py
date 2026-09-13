import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def pastas_extras():
    valor = os.getenv("PASTAS_EXTRAS_APPS", "")

    if not valor.strip():
        return []

    pastas = []

    for pedaco in valor.split(","):
        pedaco = pedaco.strip()

        if pedaco:
            pastas.append(Path(pedaco))

    return pastas


def config_schema():
    return [
        {
            "nome": "PASTAS_EXTRAS_APPS",
            "rotulo": (
                "Pastas extras pra buscar programas "
                "(separadas por vírgula)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
