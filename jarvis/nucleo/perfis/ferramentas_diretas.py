"""
Ferramentas DIRETAS: as que o cérebro tem declaradas na própria
sessão, e a lista curta que as descreve.

O PROBLEMA. Toda ferramenta declarada vai no `tools` da sessão, e um
cérebro de voz caro paga esse texto em TODO turno. Medido neste
projeto: as descrições longas das 23 ferramentas diretas eram 2.547
tokens por turno, e as seções do sistema.md que ensinavam a usá-las,
mais 3.435 — pagos inclusive no turno em que o usuário só disse "bom
dia".

A declaração não pode sair da sessão: o modelo só consegue CHAMAR uma
função que está declarada. O que dá para tirar é o texto longo.
Então, em dados/perfis/<slug>/ferramentas_diretas/:

  lista_ferramentas_diretas.md
      Uma linha por ferramenta — o que faz e quando pode ser usada.
      Essa linha SUBSTITUI a descrição longa do schema no começo de
      cada chamada. O modelo vê nome + linha curta, e é essa a lista
      que ele consulta para decidir.

  <nome_da_ferramenta>.md
      As instruções completas daquela ferramenta. Lidas só quando o
      cérebro vai usá-la, com ler_instrucao_ferramenta
      (jarvis/pacotes/agente_ferramentas/).

A DESCRIÇÃO LONGA ORIGINAL NÃO SE PERDE. Ela é guardada aqui no
momento da troca e devolvida junto com o arquivo da ferramenta. Isso
vale inclusive para as nativas do Gemini, que moram dentro de um
método do worker e não são alcançáveis de outro jeito — elas passam
por filtrar_declaracoes e são capturadas ali.

POR QUE O ESTADO VIVE NESTE MÓDULO, e não é relido do disco a cada
vez: filtrar_declaracoes é chamada pelos dois workers DENTRO do laço
de asyncio, e é documentada como função que não lê disco.
preparar_chamada, que os dois workers já rodam com asyncio.to_thread
logo antes dela, é quem carrega a lista. Ninguém bloqueia o laço de
eventos por causa disto.

PERFIS SEM A PASTA: um perfil criado pela tela de perfis nasce só com
perfil.json e sistema.md. Nesse caso tudo aqui cai para a pasta do
perfil padrão ("completo"), que é versionada no repositório e sempre
existe. Uma ferramenta sem linha na lista simplesmente mantém a
descrição longa — mais cara, nunca quebrada.

Nada aqui levanta exceção. Uma lista ilegível significa pagar mais
tokens nesta chamada, nunca uma chamada que não abre.
"""

import re

PASTA = "ferramentas_diretas"
ARQUIVO_LISTA = "lista_ferramentas_diretas.md"

# "nome_da_ferramenta: descrição". Nome em minúsculas com sublinhado,
# que é a convenção de TODA ferramenta deste projeto — uma linha fora
# desse formato é tratada como texto e ignorada, não como erro.
_PADRAO_LINHA = re.compile(r"^([a-z][a-z0-9_]*)\s*:\s*(.+?)\s*$")

# Um nome de ferramenta INTEIRO — usado antes de transformar um nome
# vindo do modelo em caminho de arquivo. fullmatch, e não match: um
# "abc: x" ou "../abc" nunca pode passar por um nome válido.
_PADRAO_NOME = re.compile(r"[a-z][a-z0-9_]*")

# Estado da chamada atual: carregado por preparar_chamada, usado por
# filtrar_declaracoes e por ler_instrucao_ferramenta.
_linhas_da_chamada = {}
_slug_da_chamada = None
_descricoes_originais = {}


def _pastas_candidatas(slug):
    """
    As pastas onde procurar, na ordem: a do perfil pedido e, se ela não
    existir, a do perfil padrão. Import adiado: este módulo é importado
    por armazenamento.py, e o contrário fecharia um ciclo.
    """
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
    """
    nome -> linha curta, lido do disco. Devolve {} se não houver lista.
    """
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
    """
    Lê a lista do perfil desta chamada para a memória. Chamado por
    preparar_chamada, fora do laço de eventos. Nunca levanta.
    """
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
    """
    Troca a descrição longa de cada ferramenta que tem linha na lista
    pela linha curta, guardando a original.

    DEVOLVE CÓPIAS, nunca altera a declaração recebida. As declarações
    de pacote são objetos de nível de módulo, compartilhados: mudar a
    descrição delas no lugar mudaria também o que o sub-agente de
    ferramentas lê como "descrição completa", para sempre, a partir da
    primeira chamada.

    Não faz nada com FERRAMENTAS_SOB_DEMANDA=false: nesse modo o
    cérebro volta a receber as descrições longas de sempre.
    """
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
            copia = declaracao.model_copy(update={"description": linha})

        except Exception:
            # Um objeto que não se deixa copiar segue com a descrição
            # longa: mais caro, e só isso.
            resultado.append(declaracao)
            continue

        _descricoes_originais[nome] = original
        resultado.append(copia)

    return resultado


def tem_na_lista(nome):
    return nome in _linhas_da_chamada


def instrucao_de(nome, slug=None):
    """
    O texto que ler_instrucao_ferramenta devolve para uma ferramenta
    direta: a descrição longa original seguida das instruções do
    arquivo dela. "" quando não há nada para essa ferramenta.

    Linhas começando com # no arquivo são cabeçalho para quem edita e
    nunca chegam ao modelo.
    """
    partes = []

    original = _descricoes_originais.get(nome, "").strip()

    if original:
        partes.append(" ".join(original.split()))

    pasta = _pasta_existente(slug or _slug_da_chamada)

    if pasta is not None:
        arquivo = pasta / f"{nome}.md"

        # O nome vem do modelo. Só um nome no formato de ferramenta
        # vira caminho — nada de "../" chegando a um arquivo de fora.
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
