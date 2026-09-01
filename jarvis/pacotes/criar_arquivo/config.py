# Configuração do pacote de criação de arquivo por voz — cada pacote
# isolado faz sua própria load_dotenv() (mesmo padrão de
# rede_jarvis/casa_inteligente), sem depender de
# jarvis/nucleo/config.py.
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Pastas onde o ALFRED tem permissão de criar arquivo por voz — NUNCA
# o disco inteiro. Configurável via .env
# (PASTAS_PERMITIDAS_CRIACAO, caminhos absolutos separados por
# vírgula); se não configurado, usa um padrão seguro (Área de
# Trabalho, Documentos e Downloads do usuário atual).
_PASTAS_PADRAO = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]


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


# Pasta usada quando o usuário não especifica onde criar o arquivo —
# sempre a primeira da lista permitida.
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
