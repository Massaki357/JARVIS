# Imports sempre adiados: este pacote está em PACOTES_REGISTRADOS (ciclo de import).
TOOLS_PROPRIAS = (
    "buscar_ferramenta",
    "executar_ferramenta",
    "ler_instrucao_ferramenta",
)

ORIGEM_PACOTE = "pacote"
ORIGEM_NATIVA = "nativa"


def _declaracoes_de_pacote():
    from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS
    from jarvis.servicos.agentes.ferramentas import normalizar_esquema

    por_nome = {}

    for pacote in PACOTES_REGISTRADOS:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            try:
                bruto = declaracao.to_json_dict()

            except Exception:
                continue

            nome = bruto.get("name")

            if not nome or nome in TOOLS_PROPRIAS:
                continue

            parametros = bruto.get("parameters") or {}

            por_nome[nome] = {
                "descricao": (bruto.get("description") or "").strip(),
                "parametros": normalizar_esquema(parametros),
            }

    return por_nome


def _nomes_permitidos():
    try:
        from jarvis.nucleo import perfis
        from jarvis.nucleo.perfis import catalogo_ferramentas

        do_perfil = set(
            perfis.ferramentas_efetivas(perfis.perfil_ativo())
        )

        do_cerebro = set(
            catalogo_ferramentas.nomes_do_cerebro(
                catalogo_ferramentas.cerebro_atual_usa_openai()
            )
        )

        permitidos = do_perfil & do_cerebro

        return permitidos or None

    except Exception as erro:
        print(
            "[agente_ferramentas] Não consegui resolver as ferramentas "
            f"do perfil ativo; usando o catálogo inteiro. ({erro})"
        )

        return None


def montar():
    from jarvis.nucleo.perfis import catalogo_ferramentas
    from jarvis.nucleo.registro_pacotes import ferramentas_ocultas

    declaracoes = _declaracoes_de_pacote()
    permitidos = _nomes_permitidos()

    try:
        ocultas = ferramentas_ocultas()

    except Exception:
        ocultas = set()

    itens = []

    for item in catalogo_ferramentas.catalogo_completo():
        nome = item["nome"]

        if nome in TOOLS_PROPRIAS:
            continue

        if permitidos is not None and nome not in permitidos:
            continue

        if ocultas and nome not in ocultas:
            continue

        resumo = item["resumo"]
        completa = declaracoes.get(nome)

        itens.append(
            {
                "nome": nome,
                "resumo": resumo,
                "descricao": (
                    completa["descricao"] if completa else resumo
                ),
                "parametros": (
                    completa["parametros"] if completa else {}
                ),
                "origem": (
                    ORIGEM_PACOTE if completa else ORIGEM_NATIVA
                ),
                "categoria": item["rotulo_categoria"],
                "oculta": nome in ocultas,
            }
        )

    return itens


def texto_para_prompt(itens, usar_descricao_completa=False):
    por_categoria = {}

    for item in itens:
        por_categoria.setdefault(item["categoria"], []).append(item)

    blocos = []

    for categoria, ferramentas in por_categoria.items():
        linhas = [f"## {categoria}"]

        for ferramenta in ferramentas:
            descricao = (
                ferramenta["descricao"]
                if usar_descricao_completa
                else ferramenta["resumo"]
            )

            descricao = " ".join(str(descricao).split())

            linhas.append(f"- {ferramenta['nome']}: {descricao}")

        blocos.append("\n".join(linhas))

    return "\n\n".join(blocos)


def procurar(itens, nome):
    for item in itens:
        if item["nome"] == nome:
            return item

    return None
