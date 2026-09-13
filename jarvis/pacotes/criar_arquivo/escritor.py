import os
import re
import unicodedata
from datetime import datetime

from . import config

LIMITE_CARACTERES_CONTEUDO = 5000

_EXTENSAO_PADRAO = "txt"


def _remover_acentos(texto):
    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )


def _nome_arquivo_seguro(nome):
    nome = os.path.basename(
        (nome or "").strip()
    )

    nome = _remover_acentos(nome)

    nome = re.sub(
        r"[^A-Za-z0-9._\- ]",
        "_",
        nome,
    )

    return nome.strip(" ._")


def _extensao_segura(extensao):
    extensao = re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(extensao or "").strip(),
    )

    extensao = extensao.lower()[:10]

    return extensao or _EXTENSAO_PADRAO


def _caminho_sem_sobrescrever(caminho):
    if not caminho.exists():
        return caminho

    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidato = caminho.with_stem(f"{caminho.stem}_{sufixo}")

    contador = 1

    while candidato.exists():
        candidato = caminho.with_stem(
            f"{caminho.stem}_{sufixo}_{contador}"
        )
        contador += 1

    return candidato


def _resolver_pasta_falada(pasta_falada, permitidas):
    alvo = _remover_acentos(pasta_falada).strip().lower()

    for pasta in permitidas:
        if _remover_acentos(pasta.name).strip().lower() == alvo:
            return pasta

    for pasta in permitidas:
        nome_pasta = _remover_acentos(pasta.name).strip().lower()

        if alvo in nome_pasta or nome_pasta in alvo:
            return pasta

    return None


def criar_arquivo(nome, conteudo, pasta_falada=None, extensao="txt"):
    nome_seguro = _nome_arquivo_seguro(nome)

    if not nome_seguro:
        return False, (
            "Nome de arquivo inválido — não sobrou nada depois de "
            "remover caracteres não permitidos."
        )

    permitidas = config.pastas_permitidas()

    if pasta_falada:
        pasta_destino = _resolver_pasta_falada(pasta_falada, permitidas)

        if pasta_destino is None:
            nomes_permitidos = ", ".join(p.name for p in permitidas)

            return False, (
                f"'{pasta_falada}' não é uma pasta permitida pra criar "
                f"arquivo. Pastas permitidas: {nomes_permitidos}."
            )

    else:
        pasta_destino = config.pasta_padrao()

    pasta_destino_resolvida = pasta_destino.resolve()

    permitido = any(
        pasta_destino_resolvida == pasta.resolve()
        for pasta in permitidas
    )

    if not permitido:
        return False, (
            f"'{pasta_destino}' não está entre as pastas permitidas "
            "pra criar arquivo."
        )

    extensao_segura = _extensao_segura(extensao)

    conteudo = conteudo or ""
    truncado = False

    if len(conteudo) > LIMITE_CARACTERES_CONTEUDO:
        conteudo = conteudo[:LIMITE_CARACTERES_CONTEUDO]
        truncado = True

    caminho_arquivo = (
        pasta_destino_resolvida / f"{nome_seguro}.{extensao_segura}"
    )

    if pasta_destino_resolvida not in caminho_arquivo.resolve().parents:
        return False, "Caminho de destino inválido."

    caminho_final = _caminho_sem_sobrescrever(caminho_arquivo)

    try:
        caminho_final.write_text(conteudo, encoding="utf-8")

    except OSError as erro:
        return False, f"Falha ao criar o arquivo: {erro}"

    mensagem = (
        f"Arquivo '{caminho_final.name}' criado em "
        f"{pasta_destino_resolvida}."
    )

    if truncado:
        mensagem += (
            f" (conteúdo truncado em {LIMITE_CARACTERES_CONTEUDO} "
            "caracteres)"
        )

    return True, mensagem
