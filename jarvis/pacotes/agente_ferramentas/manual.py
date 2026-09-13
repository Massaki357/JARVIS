"""
O manual de uso por ferramenta, entregue SOB DEMANDA.

DE ONDE ELE VEIO. Tudo aqui já existia dentro do sistema.md do
perfil, no prefixo de toda chamada: as seções "## CRIAR ARQUIVO",
"## AGENDA", "## DISCORD" e companhia, com as regras de quando usar
cada ferramenta e o que nunca fazer com ela. São 3.836 tokens
medidos, pagos em TODO turno — inclusive nos turnos em que o usuário
só falou "bom dia".

Agora elas moram em dados/perfis/<slug>/manual_ferramentas.md e
chegam ao cérebro junto com a ferramenta que o sub-agente recomendou.
A regra continua sendo a mesma, escrita com as mesmas palavras; só
deixou de ser paga quando não é usada.

O QUE **NÃO** VEIO PARA CÁ, e isso é uma decisão de segurança: as
seções que mencionam alguma ferramenta que CONTINUA DECLARADA
(EMAIL, ENVIO DE CAPTURA, VISÃO, VÍDEO AO VIVO, IDENTIFICAÇÃO
VISUAL, MOUSE, CLIQUE, ESCRITA) ficaram inteiras no sistema.md. Elas
são mistas — falam ao mesmo tempo de ferramentas declaradas e
ocultas — e recortá-las na unha significaria reescrever prosa que
carrega trava de segurança ("nunca invente destinatário", "só quando
o usuário pedir explicitamente"). Deixar 4 mil tokens na mesa é
barato perto de perder uma dessas frases sem perceber.

O MAPA ferramenta -> seção é DERIVADO, não escrito à mão: cada seção
já cita pelo nome as ferramentas de que trata, então é isso que é
procurado. Um manual que deixe de citar um nome simplesmente não é
entregue para aquela ferramenta — falha silenciosa e inofensiva, ao
contrário de um mapa desatualizado apontando para a seção errada.
"""

import re

NOME_ARQUIVO = "manual_ferramentas.md"

# Cache por (caminho, mtime): o arquivo só é relido quando muda de
# verdade. Editar o manual vale na chamada seguinte, sem reiniciar.
_cache = {}


def _caminho(slug):
    """
    O manual do perfil pedido e, se ele não tiver um, o do perfil
    padrão. Um perfil criado pela tela de perfis nasce só com
    perfil.json e sistema.md — sem este fallback, trocar para ele
    faria as regras de toda ferramenta oculta pararem de chegar ao
    cérebro, sem aviso nenhum.
    """
    from jarvis.nucleo.perfis import armazenamento

    proprio = armazenamento.caminho_do_perfil(slug) / NOME_ARQUIVO

    if proprio.exists():
        return proprio

    return (
        armazenamento.caminho_do_perfil(armazenamento.SLUG_PADRAO)
        / NOME_ARQUIVO
    )


def _secoes(texto, nomes_conhecidos):
    """
    nome_da_ferramenta -> texto da seção que fala dela.

    Uma seção pode cobrir várias ferramentas (a de agenda cita as
    quatro de agenda); todas apontam para o mesmo texto.
    """
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
    """
    O trecho de manual daquela ferramenta, ou "" se não houver.

    Ausência é normal, não erro: as ferramentas cujas regras ficaram
    no sistema.md não têm seção aqui — elas já chegam ao cérebro no
    prefixo, e repeti-las seria pagar duas vezes pelo mesmo texto.
    """
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
    """
    O que ler_instrucao_ferramenta devolve: tudo que existe sobre como
    usar aquela ferramenta, venha de onde vier.

      - ferramenta DIRETA: a descrição longa original do schema (que
        saiu da sessão, trocada pela linha curta da lista) seguida do
        arquivo de instrução dela — ver
        jarvis/nucleo/perfis/ferramentas_diretas.py;
      - ferramenta OCULTA: a seção dela neste manual. Normalmente essa
        chega pelo buscar_ferramenta, mas com
        FERRAMENTAS_SOB_DEMANDA=false tudo fica declarado, e o cérebro
        pode perguntar por qualquer uma.

    "" quando não há nada além do que o schema já diz.
    """
    from jarvis.nucleo.perfis import ferramentas_diretas

    direta = ferramentas_diretas.instrucao_de(nome_ferramenta)

    if direta:
        return direta

    return secao_de(nome_ferramenta)
