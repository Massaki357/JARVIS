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


def buscar_canal(nome_falado):
    canais = cliente.listar_canais()

    if not canais:
        return None, []

    alvo = _normalizar(nome_falado)

    exatos = [
        canal
        for canal in canais
        if _normalizar(canal["nome"]) == alvo
    ]

    if len(exatos) == 1:
        return exatos[0], None

    if len(exatos) > 1:
        return None, exatos

    parciais = [
        canal
        for canal in canais
        if alvo in _normalizar(canal["nome"])
        or _normalizar(canal["nome"]) in alvo
    ]

    if len(parciais) == 1:
        return parciais[0], None

    if len(parciais) > 1:
        return None, parciais

    canais_por_nome_normalizado = {
        _normalizar(canal["nome"]): canal
        for canal in canais
    }

    proximos = difflib.get_close_matches(
        alvo,
        canais_por_nome_normalizado.keys(),
        n=5,
        cutoff=0.72,
    )

    candidatos_aproximados = [
        canais_por_nome_normalizado[nome]
        for nome in proximos
    ]

    if len(candidatos_aproximados) == 1:
        return candidatos_aproximados[0], None

    if len(candidatos_aproximados) > 1:
        return None, candidatos_aproximados

    return None, []


def descricao_canal(canal):
    return f"#{canal['nome']} (servidor: {canal['servidor']})"
