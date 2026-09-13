from . import config, notas


def _trechos_reconheciveis(titulo):
    palavras = notas.normalizar(titulo).split()

    if not palavras:
        return []

    trechos = []

    for palavra in palavras:
        if len(palavra) >= 6 and palavra not in notas.IRRELEVANTES:
            trechos.append(palavra)

    for inicio in range(len(palavras)):
        for fim in range(inicio + 2, len(palavras) + 1):
            trecho = " ".join(palavras[inicio:fim])

            if len(trecho) < 10:
                continue

            if any(
                len(p) >= 4 and p not in notas.IRRELEVANTES
                for p in palavras[inicio:fim]
            ):
                trechos.append(trecho)

    return trechos


def detectar_relacionados(texto, titulo_propria=""):
    alvo = notas.normalizar(texto)

    if not alvo:
        return []

    propria = notas.normalizar(titulo_propria)
    encontrados = []

    for nota in notas.listar_notas():
        titulo = nota["titulo"]
        chave = notas.normalizar(titulo)

        if len(chave) < 4 or chave == propria:
            continue

        for trecho in _trechos_reconheciveis(titulo):
            if trecho in alvo:
                encontrados.append(titulo)
                break

    return encontrados


def salvar_memoria(
    titulo,
    conteudo,
    relacionados=None,
    fixar=False,
):
    if not config.configurado():
        return (
            "A pasta do vault não está configurada. Peça para "
            "definir PASTA_VAULT_JARVIS no arquivo .env."
        )

    titulo = str(titulo or "").strip()
    conteudo = str(conteudo or "").strip()

    if not titulo:
        return "Preciso de um título para guardar essa memória."

    if not conteudo:
        return "Preciso do conteúdo para guardar essa memória."

    try:
        notas.garantir_pastas()

        existentes = notas.localizar_por_titulo(
            titulo,
            incluir_arquivo=True,
        )

        nota_existente = existentes[0] if len(existentes) == 1 else None

        aviso_ambiguidade = ""

        if len(existentes) > 1:
            nomes = ", ".join(n["titulo"] for n in existentes[:5])

            aviso_ambiguidade = (
                f" (havia mais de uma nota parecida: {nomes} — "
                "criei uma nota separada em vez de adivinhar qual "
                "atualizar)"
            )

        if nota_existente is not None:
            frontmatter = dict(nota_existente["frontmatter"])
            caminho = nota_existente["caminho"]
            titulo_final = nota_existente["titulo"]
            acao = "Atualizei"

            if nota_existente["arquivada"]:
                caminho = config.PASTA_VAULT / caminho.name
                frontmatter["access_count"] = 0
                frontmatter["last_used"] = notas.agora()

                try:
                    nota_existente["caminho"].unlink()

                except OSError:
                    pass

                acao = "Reativei e atualizei"

        else:
            frontmatter = {
                "created": notas.agora(),
                "last_used": notas.agora(),
                "access_count": 0,
                "pinned": False,
            }

            titulo_final = titulo

            caminho = (
                config.PASTA_VAULT
                / notas.nome_arquivo_do_titulo(titulo)
            )

            acao = "Guardei"

        if fixar:
            frontmatter["pinned"] = True

        titulos_relacionados = list(relacionados or [])

        titulos_relacionados += detectar_relacionados(
            conteudo,
            titulo_propria=titulo_final,
        )

        if nota_existente is not None:
            titulos_relacionados += notas.extrair_links(
                nota_existente["corpo"]
            )

        corpo = notas.aplicar_relacionados(
            conteudo,
            titulos_relacionados,
        )

        notas.escrever_nota(caminho, frontmatter, corpo)

    except ValueError as erro:
        return f"Não consegui guardar essa memória: {erro}"

    except OSError as erro:
        return f"Não consegui gravar o arquivo da memória: {erro}"

    detalhe_links = ""

    if titulos_relacionados:
        unicos = []
        vistos = set()

        for item in titulos_relacionados:
            chave = notas.normalizar(item)

            if chave and chave not in vistos:
                vistos.add(chave)
                unicos.append(item)

        detalhe_links = (
            " Liguei essa nota a: " + ", ".join(unicos[:5]) + "."
        )

    fixada = " Marquei como permanente." if fixar else ""

    return (
        f"{acao} a memória '{titulo_final}'.{detalhe_links}{fixada}"
        f"{aviso_ambiguidade}"
    )


def fixar_memoria(titulo):
    if not config.configurado():
        return (
            "A pasta do vault não está configurada. Peça para "
            "definir PASTA_VAULT_JARVIS no arquivo .env."
        )

    encontradas = notas.localizar_por_titulo(
        titulo,
        incluir_arquivo=True,
    )

    if not encontradas:
        return (
            f"Não encontrei nenhuma memória parecida com '{titulo}'."
        )

    if len(encontradas) > 1:
        nomes = ", ".join(n["titulo"] for n in encontradas[:5])

        return (
            f"Encontrei mais de uma memória parecida: {nomes}. "
            "Qual delas você quer marcar como permanente?"
        )

    nota = encontradas[0]
    frontmatter = dict(nota["frontmatter"])
    frontmatter["pinned"] = True

    try:
        notas.escrever_nota(
            nota["caminho"],
            frontmatter,
            nota["corpo"],
        )

    except (ValueError, OSError) as erro:
        return f"Não consegui marcar essa memória: {erro}"

    return (
        f"Pronto: '{nota['titulo']}' agora é permanente e nunca "
        "vai ser arquivada por falta de uso."
    )
