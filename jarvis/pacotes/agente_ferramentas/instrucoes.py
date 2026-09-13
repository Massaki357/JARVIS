_TIPOS = {
    "string": "texto",
    "integer": "número inteiro",
    "number": "número",
    "boolean": "sim/não",
    "array": "lista",
    "object": "objeto",
}


def _nome_do_tipo(esquema):
    tipo = (esquema.get("type") or "").lower()
    legivel = _TIPOS.get(tipo, tipo or "texto")

    if tipo == "array":
        itens = esquema.get("items") or {}
        tipo_item = (itens.get("type") or "").lower()

        if tipo_item:
            return f"lista de {_TIPOS.get(tipo_item, tipo_item)}"

    return legivel


def _linha_de_parametro(nome, esquema, obrigatorio):
    partes = [f"- {nome} ({_nome_do_tipo(esquema)}"]

    partes.append(", OBRIGATÓRIO)" if obrigatorio else ", opcional)")

    descricao = " ".join(str(esquema.get("description") or "").split())

    if descricao:
        partes.append(f": {descricao}")

    linha = "".join(partes)

    opcoes = esquema.get("enum")

    if isinstance(opcoes, list) and opcoes:
        valores = ", ".join(str(opcao) for opcao in opcoes)
        linha += f" Valores aceitos: {valores}."

    return linha


def descrever_parametros(parametros):
    propriedades = (parametros or {}).get("properties") or {}

    if not propriedades:
        return None

    obrigatorios = set((parametros or {}).get("required") or [])

    ordenados = sorted(
        propriedades.items(),
        key=lambda item: (item[0] not in obrigatorios, item[0]),
    )

    return [
        _linha_de_parametro(nome, esquema or {}, nome in obrigatorios)
        for nome, esquema in ordenados
    ]


def montar(recomendada, alternativas, motivo, manual=""):
    nome = recomendada["nome"]

    linhas = [f"FERRAMENTA RECOMENDADA: {nome}"]

    if motivo:
        linhas.append(f"POR QUE: {motivo}")

    descricao = " ".join(str(recomendada["descricao"]).split())
    linhas.append("")
    linhas.append(f"O QUE ELA FAZ: {descricao}")

    linhas.append("")

    if recomendada["origem"] == "nativa":
        linhas.append(
            "COMO CHAMAR: esta é uma ferramenta nativa da sua sessão, "
            "então você já tem a declaração completa dela com todos os "
            "parâmetros. Use a declaração que você já conhece."
        )

    else:
        parametros = descrever_parametros(recomendada["parametros"])

        if parametros:
            linhas.append("COMO CHAMAR — parâmetros:")
            linhas.extend(parametros)

        else:
            linhas.append(
                "COMO CHAMAR: esta ferramenta não recebe nenhum "
                "parâmetro."
            )

    if alternativas:
        linhas.append("")
        linhas.append(
            "SE A RECOMENDADA NÃO SERVIR, as outras candidatas foram:"
        )

        for item in alternativas:
            resumo = " ".join(str(item["resumo"]).split())
            linhas.append(f"- {item['nome']}: {resumo}")

    if manual:
        linhas.append("")
        linhas.append("REGRAS DE USO DESTA FERRAMENTA:")
        linhas.append(manual.strip())

    linhas.append("")

    if recomendada.get("oculta"):
        linhas.append(
            "Esta ferramenta NÃO está declarada na sua sessão. Chame "
            f'executar_ferramenta agora, com nome="{nome}" e '
            "argumentos = um JSON com os parâmetros acima, preenchidos "
            "com o que o usuário pediu."
        )

    else:
        linhas.append(
            f"Agora chame {nome} DIRETO (ela já está declarada na sua "
            "sessão), preenchendo os parâmetros com o que o usuário "
            "pediu."
        )

    linhas.append(
        "Este texto é uma instrução para você — não leia nada dele em "
        "voz alta para o usuário."
    )

    return "\n".join(linhas)


def nenhuma_ferramenta(motivo):
    texto = (
        "NENHUMA FERRAMENTA SERVE para esse pedido."
    )

    if motivo:
        texto += f" Motivo: {motivo}"

    return (
        f"{texto} Se alguma função da SUA lista atende ao pedido, use "
        "ela. Se não, responda ao usuário você mesmo, sem chamar "
        "função. Não leia este texto em voz alta."
    )


# Nunca pode virar o texto de 'nenhuma ferramenta serve'.
def falha(detalhe):
    return (
        "NÃO CONSEGUI CONSULTAR o sub-agente de ferramentas agora "
        f"({detalhe}). Isso NÃO quer dizer que não existe ferramenta "
        "para o pedido — quer dizer que a busca falhou. Se você "
        "souber por conta própria qual função chamar, chame. Se não "
        "souber, diga ao usuário, em uma frase curta, que não "
        "conseguiu identificar a ferramenta desta vez e peça para ele "
        "repetir. NUNCA diga que executou a ação: nada foi executado."
    )
