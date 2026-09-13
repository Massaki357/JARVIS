import re

NOME_ARQUIVO = "manual_ferramentas.md"

_cache = {}


def _caminho(slug):
    from jarvis.nucleo.perfis import armazenamento

    proprio = armazenamento.caminho_do_perfil(slug) / NOME_ARQUIVO

    if proprio.exists():
        return proprio

    return (
        armazenamento.caminho_do_perfil(armazenamento.SLUG_PADRAO)
        / NOME_ARQUIVO
    )


def _secoes(texto, nomes_conhecidos):
    mapa = {}

    for bruto in re.split(r"(?m)^## ", texto):
        if not bruto.strip():
            continue

        secao = "## " + bruto.rstrip()

        for nome in nomes_conhecidos:
            if re.search(rf"\b{re.escape(nome)}\b", secao):
                mapa.setdefault(nome, secao)

    return mapa


def _carregar(slug):
    try:
        caminho = _caminho(slug)

        if not caminho.exists():
            return {}

        assinatura = (str(caminho), caminho.stat().st_mtime)

        if assinatura in _cache:
            return _cache[assinatura]

        from jarvis.nucleo.perfis import catalogo_ferramentas

        mapa = _secoes(
            caminho.read_text(encoding="utf-8"),
            set(catalogo_ferramentas.nomes_disponiveis()),
        )

        _cache.clear()
        _cache[assinatura] = mapa

        return mapa

    except Exception as erro:
        print(
            f"[agente_ferramentas] Não consegui ler o {NOME_ARQUIVO} "
            f"do perfil '{slug}': {erro}"
        )

        return {}


def secao_de(nome_ferramenta, slug=None):
    if not nome_ferramenta:
        return ""

    try:
        if slug is None:
            from jarvis.nucleo import perfis

            slug = perfis.perfil_ativo()

    except Exception:
        return ""

    return _carregar(slug).get(nome_ferramenta, "")


def instrucao_completa(nome_ferramenta):
    from jarvis.nucleo.perfis import ferramentas_diretas

    direta = ferramentas_diretas.instrucao_de(nome_ferramenta)

    if direta:
        return direta

    return secao_de(nome_ferramenta)
