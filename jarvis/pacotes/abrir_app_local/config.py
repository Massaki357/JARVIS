# Configuração do pacote de abertura de app local. Cada pacote
# isolado faz sua própria load_dotenv() (mesmo padrão de
# rede_jarvis/casa_inteligente), sem depender de
# jarvis/nucleo/config.py.
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# Pastas extras (fora do Get-StartApps) onde também procurar
# executáveis — ex: onde o usuário guarda programas portáteis que
# nunca aparecem na busca do menu Iniciar. Configurável via .env
# (PASTAS_EXTRAS_APPS, caminhos absolutos separados por vírgula);
# opcional — vazio significa "só o Get-StartApps mesmo", igual antes
# desta extensão existir.
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
