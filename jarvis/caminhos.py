from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

CAMINHO_ENV = RAIZ_PROJETO / ".env"

CAMINHO_CONFIG_JSON = RAIZ_PROJETO / "config.json"

PASTA_JARVIS = Path(__file__).resolve().parent

PASTA_DADOS = RAIZ_PROJETO / "dados"
PASTA_LOGS = PASTA_DADOS / "logs"

PASTA_PERFIS = PASTA_DADOS / "perfis"


def garantir_pasta(caminho):
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho
