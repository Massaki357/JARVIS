import difflib
import re
import unicodedata

from . import cliente


def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def _nomes_do_membro(membro):
    return [
        nome
        for nome in (
            membro["apelido"],
            membro["nome_exibicao"],
            membro["username"],
        )
        if nome
    ]


def buscar_membro(nome_falado):
    membros = cliente.listar_membros()

    if not membros:
        return None, []

    alvo = _normalizar(nome_falado)

    exatos = [
        membro
        for membro in membros
        if any(
            _normalizar(nome) == alvo
            for nome in _nomes_do_membro(membro)
        )
    ]

    if len(exatos) == 1:
        return exatos[0], None

    if len(exatos) > 1:
        return None, exatos

    parciais = [
        membro
        for membro in membros
        if any(
            alvo in _normalizar(nome) or _normalizar(nome) in alvo
            for nome in _nomes_do_membro(membro)
        )
    ]

    if len(parciais) == 1:
        return parciais[0], None

    if len(parciais) > 1:
        return None, parciais

    membros_por_nome_normalizado = {}

    for membro in membros:
        for nome in _nomes_do_membro(membro):
            membros_por_nome_normalizado[_normalizar(nome)] = membro

    proximos = difflib.get_close_matches(
        alvo,
        membros_por_nome_normalizado.keys(),
        n=5,
        cutoff=0.72,
    )

    candidatos_aproximados = [
        membros_por_nome_normalizado[nome]
        for nome in proximos
    ]

    if len(candidatos_aproximados) == 1:
        return candidatos_aproximados[0], None

    if len(candidatos_aproximados) > 1:
        return None, candidatos_aproximados

    return None, []


def descricao_membro(membro):
    if membro["apelido"] and membro["apelido"] != membro["nome_exibicao"]:
        return (
            f"{membro['nome_exibicao']} (apelido: {membro['apelido']}, "
            f"@{membro['username']})"
        )

    return f"{membro['nome_exibicao']} (@{membro['username']})"
