# Leitura e escrita do .env — usado só pela tela de configurações.
# Nunca reescreve o arquivo inteiro: dotenv_values só LÊ (não toca no
# arquivo), e set_key atualiza/adiciona UMA variável por vez,
# preservando comentários, ordem e as demais variáveis intactas.
from dotenv import dotenv_values, set_key

# Caminho vem de jarvis/caminhos.py — nunca calculado aqui, pra
# não depender de quantos níveis este arquivo está abaixo da raiz.
from jarvis.caminhos import CAMINHO_ENV


# Retorna {nome_variavel: valor} com tudo que está no .env agora. Uma
# variável ausente do arquivo simplesmente não aparece no dict — não
# confundir com uma variável presente mas com valor vazio ('KEY=').
# Se o arquivo ainda não existir, retorna vazio (a tela deve tratar
# isso como "nenhum valor preenchido ainda", não como erro).
def ler_valores():
    if not CAMINHO_ENV.exists():
        return {}

    valores = dotenv_values(CAMINHO_ENV)

    return {chave: (valor or "") for chave, valor in valores.items()}


# Grava UM valor no .env, sem tocar no resto do arquivo. Cria o
# arquivo primeiro se ainda não existir (set_key exige que o arquivo
# já exista). quote_mode="never" mantém o mesmo estilo sem aspas já
# usado nas variáveis existentes do projeto.
def salvar_valor(nome, valor):
    CAMINHO_ENV.touch(exist_ok=True)

    set_key(
        str(CAMINHO_ENV),
        nome,
        valor,
        quote_mode="never",
    )
