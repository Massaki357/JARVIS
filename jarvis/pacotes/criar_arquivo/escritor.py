import os
import re
import unicodedata
from datetime import datetime

from . import config

LIMITE_CARACTERES_CONTEUDO = 5000

_EXTENSAO_PADRAO = "txt"

# O Windows grava as pastas em inglês; o usuário e o modelo falam em português.
_NOMES_EM_PORTUGUES = {
    "desktop": ("area de trabalho",),
    "documents": ("documentos", "meus documentos"),
    "downloads": ("transferencias",),
}

_NOME_EXIBIDO = {
    "desktop": "Área de Trabalho",
    "documents": "Documentos",
}

_MINIMO_CARACTERES_PARCIAL = 4


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


def _normalizar(texto):
    return " ".join(_remover_acentos(str(texto or "")).lower().split())


def _nomes_da_pasta(pasta):
    nome = _normalizar(pasta.name)

    return (nome,) + _NOMES_EM_PORTUGUES.get(nome, ())


def _resolver_pasta_falada(pasta_falada, permitidas):
    alvo = _normalizar(pasta_falada)

    if not alvo:
        return None

    for pasta in permitidas:
        if alvo in _nomes_da_pasta(pasta):
            return pasta

    for pasta in permitidas:
        for nome_pasta in _nomes_da_pasta(pasta):
            if nome_pasta in alvo or (
                len(alvo) >= _MINIMO_CARACTERES_PARCIAL and alvo in nome_pasta
            ):
                return pasta

    return None


def _descrever_permitidas(permitidas):
    descricoes = []

    for pasta in permitidas:
        exibido = _NOME_EXIBIDO.get(_normalizar(pasta.name))

        descricoes.append(
            f"{exibido} ({pasta.name})" if exibido else pasta.name
        )

    return ", ".join(descricoes)


def criar_arquivo(nome, conteudo, pasta_falada=None, extensao="txt"):
    nome_seguro = _nome_arquivo_seguro(nome)

    if not nome_seguro:
        return False, (
            "NÃO criei o arquivo: nome de arquivo inválido — não sobrou "
            "nada depois de remover caracteres não permitidos."
        )

    permitidas = config.pastas_permitidas()

    if pasta_falada:
        pasta_destino = _resolver_pasta_falada(pasta_falada, permitidas)

        if pasta_destino is None:
            return False, (
                f"NÃO criei o arquivo: '{pasta_falada}' não é uma pasta "
                "permitida pra criar arquivo. Pastas permitidas: "
                f"{_descrever_permitidas(permitidas)}."
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
            f"NÃO criei o arquivo: '{pasta_destino}' não está entre as "
            "pastas permitidas pra criar arquivo."
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
        return False, "NÃO criei o arquivo: caminho de destino inválido."

    caminho_final = _caminho_sem_sobrescrever(caminho_arquivo)

    try:
        caminho_final.write_text(conteudo, encoding="utf-8")

    except OSError as erro:
        return False, f"NÃO criei o arquivo: falha ao gravar ({erro})."

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
