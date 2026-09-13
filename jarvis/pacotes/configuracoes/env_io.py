from dotenv import dotenv_values, set_key

from jarvis.caminhos import CAMINHO_ENV


def ler_valores():
    if not CAMINHO_ENV.exists():
        return {}

    valores = dotenv_values(CAMINHO_ENV)

    return {chave: (valor or "") for chave, valor in valores.items()}


def salvar_valor(nome, valor):
    CAMINHO_ENV.touch(exist_ok=True)

    set_key(
        str(CAMINHO_ENV),
        nome,
        valor,
        quote_mode="never",
    )
