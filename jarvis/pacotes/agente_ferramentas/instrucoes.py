"""
Monta o texto que volta para o cérebro.

Este arquivo é a parte do pacote que cumpre o requisito de "devolver
a ferramenta descrevendo exatamente como executá-la". O cérebro não
recebe só um nome: recebe o que a ferramenta faz, cada parâmetro com
tipo, obrigatoriedade e descrição, e as alternativas descartadas —
tudo lido da types.FunctionDeclaration real do pacote, nunca redigitado
aqui.

Todo o texto é escrito PARA UM MODELO LER, não para ser falado. A
última linha de cada resposta lembra isso explicitamente, porque a
instrução de sistema deste projeto manda o assistente narrar o
resultado de toda função — e narrar um manual de parâmetros em voz
alta seria péssimo.
"""

# Tradução dos tipos do esquema JSON para o português que o resto das
# descrições deste projeto usa. Um tipo desconhecido aparece como
# veio: inventar um nome bonito para ele esconderia o problema.
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

    # Valores fechados são a informação mais útil que existe sobre um
    # parâmetro, e a mais fácil de o modelo errar sozinho.
    opcoes = esquema.get("enum")

    if isinstance(opcoes, list) and opcoes:
        valores = ", ".join(str(opcao) for opcao in opcoes)
        linha += f" Valores aceitos: {valores}."

    return linha


def descrever_parametros(parametros):
    """
    As linhas de "como chamar" a partir do esquema de parâmetros.
    Devolve None quando a ferramenta não tem parâmetro nenhum.
    """
    propriedades = (parametros or {}).get("properties") or {}

    if not propriedades:
        return None

    obrigatorios = set((parametros or {}).get("required") or [])

    # Obrigatórios primeiro: é a ordem em que o cérebro precisa
    # pensar neles para conseguir montar a chamada.
    ordenados = sorted(
        propriedades.items(),
        key=lambda item: (item[0] not in obrigatorios, item[0]),
    )

    return [
        _linha_de_parametro(nome, esquema or {}, nome in obrigatorios)
        for nome, esquema in ordenados
    ]


def montar(recomendada, alternativas, motivo, manual=""):
    """
    A resposta completa para o cérebro quando uma ferramenta foi
    encontrada.

    `recomendada` e os itens de `alternativas` são dicts do
    catalogo.montar(); `motivo` é a frase que o sub-agente escreveu;
    `manual` é a seção de regras daquela ferramenta que saiu do
    sistema.md (ver manual.py) — vazia quando as regras dela já estão
    no prefixo do cérebro, porque repetir seria pagar duas vezes pelo
    mesmo texto.
    """
    nome = recomendada["nome"]

    linhas = [f"FERRAMENTA RECOMENDADA: {nome}"]

    if motivo:
        linhas.append(f"POR QUE: {motivo}")

    descricao = " ".join(str(recomendada["descricao"]).split())
    linhas.append("")
    linhas.append(f"O QUE ELA FAZ: {descricao}")

    linhas.append("")

    if recomendada["origem"] == "nativa":
        # Sem esquema para mostrar — e não faz falta: a declaração
        # nativa completa já está na sessão do próprio cérebro.
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

    # As regras de uso que saíram do prompt de sistema. Vêm DEPOIS do
    # "como chamar" e ANTES da ordem final, que é onde o modelo mais
    # presta atenção: são elas que carregam os "nunca faça X" de cada
    # ferramenta.
    if manual:
        linhas.append("")
        linhas.append("REGRAS DE USO DESTA FERRAMENTA:")
        linhas.append(manual.strip())

    linhas.append("")

    if recomendada.get("oculta"):
        # Oculta = não está declarada na sessão. Mandá-lo chamar
        # direto queimaria um turno inteiro com uma função que, para
        # ele, não existe.
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
    """
    Resposta quando o sub-agente concluiu que nenhuma ferramenta
    serve. É um resultado legítimo, não uma falha — e precisa ficar
    claro para o cérebro que ele deve seguir respondendo por conta
    própria em vez de tentar adivinhar uma ferramenta.
    """
    texto = (
        "NENHUMA FERRAMENTA SERVE para esse pedido."
    )

    if motivo:
        texto += f" Motivo: {motivo}"

    # O sub-agente só enxerga as ferramentas OCULTAS. Se o cérebro
    # pulou a própria lista e veio direto para cá com um pedido que era
    # de uma ferramenta direta ("olha minha tela"), "nenhuma serve"
    # levaria ele a responder sem agir. A primeira frase abaixo é a
    # rede de segurança para esse caso.
    return (
        f"{texto} Se alguma função da SUA lista atende ao pedido, use "
        "ela. Se não, responda ao usuário você mesmo, sem chamar "
        "função. Não leia este texto em voz alta."
    )


def falha(detalhe):
    """
    Resposta quando o sub-agente NÃO PÔDE ser consultado (sem chave,
    a Groq falhou, o catálogo não carregou).

    Nunca pode ser confundida com "nenhuma ferramenta serve": são
    coisas opostas. Este projeto já pagou por essa confusão uma vez —
    uma falha de roteamento tratada como conversa fez o assistente
    dizer que estava abrindo o navegador enquanto nada abria (ver
    ResultadoTurno.falhou em jarvis/roteamento_hierarquico/
    roteador.py). Por isso o texto aqui manda explicitamente NÃO
    fingir que a ação aconteceu.
    """
    return (
        "NÃO CONSEGUI CONSULTAR o sub-agente de ferramentas agora "
        f"({detalhe}). Isso NÃO quer dizer que não existe ferramenta "
        "para o pedido — quer dizer que a busca falhou. Se você "
        "souber por conta própria qual função chamar, chame. Se não "
        "souber, diga ao usuário, em uma frase curta, que não "
        "conseguiu identificar a ferramenta desta vez e peça para ele "
        "repetir. NUNCA diga que executou a ação: nada foi executado."
    )
