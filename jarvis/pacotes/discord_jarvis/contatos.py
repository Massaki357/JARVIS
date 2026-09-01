# Busca membros dos servidores em que o bot está, por nome falado.
# Mesma técnica de correspondência aproximada já usada em
# jarvis/pacotes/abrir_app_local/buscador.py (normalização acento/caixa-insensível
# + exato -> parcial -> difflib) — copiada aqui, não importada de
# outro pacote: cada pacote isolado deste projeto mantém sua própria
# cópia dessa lógica de propósito (mesmo padrão de jarvis/servicos/email/,
# jarvis/pacotes/casa_inteligente/, jarvis/pacotes/admin_terminal/, etc. — ver CLAUDE.md, "cada
# pacote isolado, sem compartilhar lógica entre si").
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


# Nomes possíveis de um membro pra comparar contra a fala do usuário
# — apelido do servidor, nome de exibição, e username (todos podem
# ser o que a pessoa falou).
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


# Encontra o(s) membro(s) cujo nome mais se aproxima de nome_falado.
# Retorna (candidato, None) se achar exatamente um; (None,
# candidatos) se achar mais de um (lista de dicts, pra desambiguar);
# (None, []) se não achar nenhum. Nunca escolhe sozinho quando há
# ambiguidade.
def buscar_membro(nome_falado):
    membros = cliente.listar_membros()

    if not membros:
        return None, []

    alvo = _normalizar(nome_falado)

    # Primeira tentativa: correspondência exata (em qualquer um dos
    # nomes possíveis do membro).
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

    # Segunda tentativa: correspondência parcial (substring, em
    # qualquer direção).
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

    # Terceira tentativa: correspondência aproximada, tolerando
    # pequenas imprecisões do reconhecimento de voz.
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


# Descrição de um membro pra mostrar numa lista de desambiguação —
# nome de exibição + apelido (se diferente) + username (identificador
# único e estável, já que a maioria das contas do Discord não usa
# mais tag numérica de 4 dígitos).
def descricao_membro(membro):
    if membro["apelido"] and membro["apelido"] != membro["nome_exibicao"]:
        return (
            f"{membro['nome_exibicao']} (apelido: {membro['apelido']}, "
            f"@{membro['username']})"
        )

    return f"{membro['nome_exibicao']} (@{membro['username']})"
