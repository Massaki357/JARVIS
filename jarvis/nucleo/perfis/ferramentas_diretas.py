import re

PASTA = "ferramentas_diretas"
ARQUIVO_LISTA = "lista_ferramentas_diretas.md"

_PADRAO_LINHA = re.compile(r"^([a-z][a-z0-9_]*)\s*:\s*(.+?)\s*$")

_PADRAO_NOME = re.compile(r"[a-z][a-z0-9_]*")

_linhas_da_chamada = {}
_slug_da_chamada = None
_descricoes_originais = {}


def _pastas_candidatas(slug):
    from . import armazenamento

    candidatas = []

    for alvo in (slug, armazenamento.SLUG_PADRAO):
        if not alvo:
            continue

        try:
            pasta = armazenamento.caminho_do_perfil(alvo) / PASTA

        except ValueError:
            continue

        if pasta not in candidatas:
            candidatas.append(pasta)

    return candidatas


def _pasta_existente(slug):
    for pasta in _pastas_candidatas(slug):
        if pasta.is_dir():
            return pasta

    return None


def ler_lista(slug):
    pasta = _pasta_existente(slug)

    if pasta is None:
        return {}

    arquivo = pasta / ARQUIVO_LISTA

    try:
        texto = arquivo.read_text(encoding="utf-8")

    except OSError:
        return {}

    linhas = {}

    for bruta in texto.splitlines():
        if bruta.lstrip().startswith("#"):
            continue

        encontrado = _PADRAO_LINHA.match(bruta)

        if encontrado:
            linhas[encontrado.group(1)] = encontrado.group(2)

    return linhas


def carregar_para_chamada(slug):
    global _linhas_da_chamada, _slug_da_chamada

    try:
        _linhas_da_chamada = ler_lista(slug)

    except Exception as erro:
        print(
            "[PERFIL] Não consegui ler a lista de ferramentas diretas; "
            f"as descrições longas serão usadas nesta chamada. ({erro})"
        )

        _linhas_da_chamada = {}

    _slug_da_chamada = slug
    _descricoes_originais.clear()


def aplicar_descricoes_curtas(declaracoes):
    from jarvis.nucleo.config import FERRAMENTAS_SOB_DEMANDA

    if not FERRAMENTAS_SOB_DEMANDA or not _linhas_da_chamada:
        return list(declaracoes)

    resultado = []

    for declaracao in declaracoes:
        nome = getattr(declaracao, "name", None)
        linha = _linhas_da_chamada.get(nome)

        if not linha:
            resultado.append(declaracao)
            continue

        try:
            original = getattr(declaracao, "description", None) or ""
            # Cópia, nunca no lugar: declarações de pacote são compartilhadas com o sub-agente.
            copia = declaracao.model_copy(update={"description": linha})

        except Exception:
            resultado.append(declaracao)
            continue

        _descricoes_originais[nome] = original
        resultado.append(copia)

    return resultado


def tem_na_lista(nome):
    return nome in _linhas_da_chamada


def instrucao_de(nome, slug=None):
    partes = []

    original = _descricoes_originais.get(nome, "").strip()

    if original:
        partes.append(" ".join(original.split()))

    pasta = _pasta_existente(slug or _slug_da_chamada)

    if pasta is not None:
        arquivo = pasta / f"{nome}.md"

        # O nome vem do modelo: fullmatch antes de virar caminho de arquivo.
        if _PADRAO_NOME.fullmatch(str(nome or "")) and arquivo.is_file():
            try:
                texto = arquivo.read_text(encoding="utf-8")

            except OSError:
                texto = ""

            corpo = "\n".join(
                linha
                for linha in texto.splitlines()
                if not linha.lstrip().startswith("#")
            ).strip()

            if corpo:
                partes.append(corpo)

    return "\n\n".join(partes)
