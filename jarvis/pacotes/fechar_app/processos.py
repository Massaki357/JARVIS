import difflib
import re
import unicodedata

import psutil


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

    texto = texto.replace("-", " ")

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def listar_nomes_processos():
    nomes = set()

    for processo in psutil.process_iter(["name"]):
        try:
            nome = processo.info.get("name")

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        if nome:
            nomes.add(nome)

    return nomes


def buscar_processo(nome_falado):
    nomes = listar_nomes_processos()

    if not nomes:
        return None, []

    alvo = _normalizar(nome_falado)

    nomes_por_normalizado = {}

    for nome in nomes:
        nomes_por_normalizado.setdefault(
            _normalizar(nome),
            [],
        ).append(nome)

    if alvo in nomes_por_normalizado:
        candidatos = nomes_por_normalizado[alvo]

        if len(candidatos) == 1:
            return candidatos[0], None

        return None, candidatos

    parciais = [
        nome
        for normalizado, lista in nomes_por_normalizado.items()
        for nome in lista
        if alvo in normalizado or normalizado in alvo
    ]

    if len(parciais) == 1:
        return parciais[0], None

    if len(parciais) > 1:
        return None, parciais

    proximos = difflib.get_close_matches(
        alvo,
        nomes_por_normalizado.keys(),
        n=5,
        cutoff=0.72,
    )

    candidatos_aproximados = [
        nome
        for normalizado in proximos
        for nome in nomes_por_normalizado[normalizado]
    ]

    if len(candidatos_aproximados) == 1:
        return candidatos_aproximados[0], None

    if len(candidatos_aproximados) > 1:
        return None, candidatos_aproximados

    return None, []
