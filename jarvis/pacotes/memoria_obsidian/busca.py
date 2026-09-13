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


def pontuar_nota(nota, termos_consulta):
    if not termos_consulta:
        return 0

    termos_titulo = _termos(nota["titulo"])
    termos_corpo = _termos(nota["corpo"])

    pontos = 3 * len(termos_consulta & termos_titulo)
    pontos += len(termos_consulta & termos_corpo)

    return pontos


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

    if not resultados:
        from . import consolidacao

        reativadas = consolidacao.reativar_por_consulta(consulta)

        if reativadas:
            resultados = buscar_memorias(consulta, limite=limite)

    return formatar_resultado(consulta, resultados)


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
