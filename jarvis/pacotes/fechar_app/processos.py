# Lista e resolve processos em execução pelo nome falado, pra fechar
# um aplicativo aberto por voz. Mesma técnica de normalização e
# correspondência aproximada (accent/case fold, substring, difflib
# cutoff 0.72) já usada em jarvis/pacotes/abrir_app_local/buscador.py
# — copiada aqui, não importada: pacote isolado, mesmo princípio de
# duplicação deliberada já usado no resto do projeto (cada pacote
# mantém sua própria cópia de _normalizar). Nunca fecha nada fora dos
# processos que o próprio psutil já enxerga rodando — sem nome ou
# comando arbitrário vindo direto da fala.
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


# Retorna o conjunto de nomes de processo (ex: "chrome.exe")
# atualmente em execução. Nunca lança exceção — processos que somem
# ou negam acesso durante a varredura são simplesmente ignorados.
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


# Resolve nome_falado para um nome de processo real em execução.
# Retorna (nome_processo, None) se achar exatamente um nome de app;
# (None, candidatos) se achar mais de um nome DIFERENTE parecido
# (lista de strings, pra desambiguar); (None, []) se não achar
# nenhum. Nunca escolhe sozinho quando há ambiguidade real entre
# apps diferentes — a decisão de fechar TODOS os processos de um
# mesmo nome já resolvido (ex: várias janelas do mesmo navegador)
# fica por conta de quem chama esta função.
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

    # Primeira tentativa: correspondência exata.
    if alvo in nomes_por_normalizado:
        candidatos = nomes_por_normalizado[alvo]

        if len(candidatos) == 1:
            return candidatos[0], None

        return None, candidatos

    # Segunda tentativa: correspondência parcial (substring, em
    # qualquer direção).
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

    # Terceira tentativa: correspondência aproximada, tolerando
    # pequenas imprecisões do reconhecimento de voz.
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
