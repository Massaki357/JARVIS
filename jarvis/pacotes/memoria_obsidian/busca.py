# Busca de memórias por palavra-chave.
#
# Nesta primeira versão a relevância é contagem de termos em comum
# entre a consulta e o título+corpo da nota — sem embedding, sem busca
# semântica. É o suficiente para um vault pessoal de dezenas ou
# poucas centenas de notas, e não adiciona dependência nem latência.
# Se ficar claro no uso que palavra-chave não basta, trocar o cálculo
# de pontuar_nota() é a única mudança necessária: nada mais neste
# arquivo depende de COMO a pontuação é feita.
#
# Duas coisas acontecem além do ranqueamento simples:
#
#   - Os resultados trazem junto os títulos das notas LINKADAS a
#     partir deles (um nível). É o que faz o vault valer mais que uma
#     lista: perguntar sobre "Gabriel" traz também o que está ligado a
#     ele, mesmo que a nota ligada não tenha nenhuma palavra da
#     consulta.
#   - Toda nota devolvida como relevante conta como usada
#     (last_used e access_count), o que a tira do caminho de poda.
import re

from . import config, notas

def _termos(texto):
    palavras = re.findall(
        r"[a-z0-9]+",
        notas.normalizar(texto),
    )

    return {
        palavra
        for palavra in palavras
        if len(palavra) > 2 and palavra not in notas.IRRELEVANTES
    }


# Pontuação de uma nota para uma consulta. O título pesa mais que o
# corpo: uma nota chamada "Email do Gabriel" deve ganhar de outra que
# só menciona Gabriel de passagem.
def pontuar_nota(nota, termos_consulta):
    if not termos_consulta:
        return 0

    termos_titulo = _termos(nota["titulo"])
    termos_corpo = _termos(nota["corpo"])

    pontos = 3 * len(termos_consulta & termos_titulo)
    pontos += len(termos_consulta & termos_corpo)

    return pontos


# Busca as notas mais relevantes. Devolve uma lista de dicts:
#   {titulo, corpo, pontuacao, relacionadas: [títulos]}
#
# registrar: quando True (padrão), marca as notas devolvidas como
# usadas. As chamadas internas que só querem inspecionar passam False,
# para não inflar access_count sem o usuário ter visto nada.
def buscar_memorias(
    consulta,
    limite=None,
    registrar=True,
):
    if not config.configurado():
        return []

    limite = limite or config.LIMITE_BUSCA_PADRAO
    termos_consulta = _termos(consulta)

    if not termos_consulta:
        return []

    pontuadas = []

    for nota in notas.listar_notas():
        pontos = pontuar_nota(nota, termos_consulta)

        if pontos > 0:
            pontuadas.append((pontos, nota))

    # Empate resolvido pela mais recentemente usada — entre duas notas
    # igualmente relevantes, a mais viva é a mais provável de servir.
    pontuadas.sort(
        key=lambda par: (
            par[0],
            str(par[1]["frontmatter"].get("last_used", "")),
        ),
        reverse=True,
    )

    resultados = []

    for pontos, nota in pontuadas[:limite]:
        if registrar:
            notas.registrar_uso(nota["caminho"])

        resultados.append(
            {
                "titulo": nota["titulo"],
                "corpo": nota["corpo"],
                "pontuacao": pontos,
                "relacionadas": notas.extrair_links(nota["corpo"]),
            }
        )

    return resultados


# Monta o texto que volta pro modelo como resultado da tool. Inclui o
# conteúdo das notas encontradas e, ao final, os títulos ligados a
# elas — um nível de profundidade, como contexto adicional que o
# modelo pode pedir depois se precisar.
def formatar_resultado(consulta, resultados):
    if not resultados:
        return (
            f"Não encontrei nenhuma memória sobre '{consulta}'. "
            "Responda com o que você já sabe e não invente que "
            "lembra de algo."
        )

    partes = [
        f"Encontrei {len(resultados)} memória(s) sobre '{consulta}':"
    ]

    ligadas = []

    for indice, resultado in enumerate(resultados, start=1):
        corpo = resultado["corpo"]

        # Corta a seção de links do corpo mostrado: os títulos ligados
        # já são listados à parte, logo abaixo.
        posicao = corpo.find("## Relacionados")

        if posicao != -1:
            corpo = corpo[:posicao].strip()

        partes.append(
            f"{indice}. {resultado['titulo']}: {corpo}"
        )

        for titulo in resultado["relacionadas"]:
            if titulo not in ligadas:
                ligadas.append(titulo)

    if ligadas:
        partes.append(
            "Notas ligadas a essas (peça de novo se precisar do "
            "conteúdo delas): " + ", ".join(ligadas[:10]) + "."
        )

    return "\n".join(partes)


# Tool de voz: buscar_memorias_relacionadas(consulta).
def buscar_e_formatar(consulta, limite=None):
    if not config.configurado():
        return (
            "A pasta do vault não está configurada. Peça para "
            "definir PASTA_VAULT_JARVIS no arquivo .env."
        )

    consulta = str(consulta or "").strip()

    if not consulta:
        return "Sobre o que você quer que eu procure na memória?"

    resultados = buscar_memorias(consulta, limite=limite)

    # Nada na pasta ativa: talvez esteja arquivada. Uma nota do
    # arquivo/ citada agora "reativou" — volta pra pasta principal em
    # vez de ficar a caminho da consolidação.
    if not resultados:
        from . import consolidacao

        reativadas = consolidacao.reativar_por_consulta(consulta)

        if reativadas:
            resultados = buscar_memorias(consulta, limite=limite)

    return formatar_resultado(consulta, resultados)


# Lista as N notas atualizadas mais recentemente, para o contexto
# inicial leve da sessão. NÃO registra uso: carregar uma nota
# automaticamente no começo da conversa não é o usuário tê-la
# acessado, e contar isso como acesso deixaria o critério de poda sem
# sentido (nada nunca envelheceria).
def contexto_inicial(quantidade=None):
    if not config.configurado():
        return ""

    quantidade = quantidade or config.NOTAS_CONTEXTO_INICIAL

    todas = notas.listar_notas()

    if not todas:
        return ""

    todas.sort(
        key=lambda nota: str(
            nota["frontmatter"].get("last_used", "")
        ),
        reverse=True,
    )

    linhas = []

    for nota in todas[:quantidade]:
        corpo = nota["corpo"]

        posicao = corpo.find("## Relacionados")

        if posicao != -1:
            corpo = corpo[:posicao].strip()

        corpo = re.sub(r"\s+", " ", corpo).strip()

        linhas.append(f"- {nota['titulo']}: {corpo[:200]}")

    return (
        f"Você tem {len(todas)} memórias guardadas. As mais "
        "recentes são: " + " ".join(linhas)
    )
