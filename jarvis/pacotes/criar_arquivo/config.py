import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PASTAS_PADRAO = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]


# Pasta falada só resolve contra esta lista, nunca como caminho cru.
def pastas_permitidas():
    valor = os.getenv("PASTAS_PERMITIDAS_CRIACAO", "")

    if not valor.strip():
        return list(_PASTAS_PADRAO)

    pastas = []

    for pedaco in valor.split(","):
        pedaco = pedaco.strip()

        if pedaco:
            pastas.append(Path(pedaco).resolve())

    return pastas or list(_PASTAS_PADRAO)


def pasta_padrao():
    pastas = pastas_permitidas()

    return pastas[0] if pastas else _PASTAS_PADRAO[0].resolve()


def config_schema():
    return [
        {
            "nome": "PASTAS_PERMITIDAS_CRIACAO",
            "rotulo": (
                "Pastas onde posso criar arquivo por voz "
                "(caminhos separados por vírgula)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
