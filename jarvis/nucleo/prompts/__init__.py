from datetime import datetime
from pathlib import Path

from jarvis.nucleo.config import obter_nome_jarvis

_PASTA = Path(__file__).resolve().parent


def _carregar_arquivo(caminho_relativo):
    return (_PASTA / caminho_relativo).read_text(
        encoding="utf-8"
    ).rstrip("\n")


ANUNCIO_ESPONTANEO = _carregar_arquivo("geral/anuncio_espontaneo.md")

ANALISE_IMAGEM_PONTUAL = _carregar_arquivo("geral/analise_imagem_pontual.md")

SAUDACAO_ATIVACAO_POR_VOZ = _carregar_arquivo(
    "geral/saudacao_ativacao_por_voz.md"
)


CRUZAMENTO_SEGUNDA_OPINIAO = _carregar_arquivo(
    "gemini/cruzamento_segunda_opiniao.md"
)


CONTEXTO_IMAGEM_ENVIADA = _carregar_arquivo(
    "geral/contexto_imagem_enviada.md"
)

CONTEXTO_ARQUIVO_ENVIADO = _carregar_arquivo(
    "geral/contexto_arquivo_enviado.md"
)


DELEGACAO_INDISPONIVEL = _carregar_arquivo("geral/delegacao_indisponivel.md")

DELEGACAO_SEGUNDA_OPINIAO_INDISPONIVEL = _carregar_arquivo(
    "geral/delegacao_segunda_opiniao_indisponivel.md"
)

DELEGACAO_SEGUNDA_OPINIAO_RESULTADO = _carregar_arquivo(
    "geral/delegacao_segunda_opiniao_resultado.md"
)


DESCRICAO_VISUAL_INSTRUCAO = _carregar_arquivo(
    "local/descricao_visual_instrucao.md"
)

DESCRICAO_VISUAL_PERGUNTA_PADRAO = _carregar_arquivo(
    "local/descricao_visual_pergunta_padrao.md"
)

DESCRICAO_VISUAL_INDISPONIVEL = _carregar_arquivo(
    "local/descricao_visual_indisponivel.md"
)


CONTEXTO_MEMORIAS_INTRO = _carregar_arquivo("local/contexto_memorias_intro.md")


VISAO_PERGUNTA_PADRAO = _carregar_arquivo("geral/visao_pergunta_padrao.md")

VISAO_INDISPONIVEL = _carregar_arquivo("geral/visao_indisponivel.md")


CONSOLIDACAO_RESUMO_ARQUIVO = _carregar_arquivo(
    "geral/consolidacao_resumo_arquivo.md"
)

CONSOLIDACAO_RESUMO_CONVERSA = _carregar_arquivo(
    "geral/consolidacao_resumo_conversa.md"
)


ROTEAMENTO_ETAPA1_INSTRUCAO = _carregar_arquivo(
    "geral/roteamento_etapa1_instrucao.md"
)

ROTEAMENTO_ETAPA2_INSTRUCAO = _carregar_arquivo(
    "geral/roteamento_etapa2_instrucao.md"
)


AGENTE_FERRAMENTAS_BUSCA = _carregar_arquivo(
    "geral/agente_ferramentas_busca.md"
)


def _montar_texto(texto_bruto):
    linhas = str(texto_bruto or "").split("\n")

    partes = [
        linha.strip()
        for linha in linhas
        if linha.strip() and not linha.strip().startswith("##")
    ]

    texto = "".join(parte + " " for parte in partes)

    return texto.replace("ALFRED", obter_nome_jarvis())


def _carregar_prosa(caminho_relativo):
    return _montar_texto(
        (_PASTA / caminho_relativo).read_text(encoding="utf-8")
    )


def instrucao_sistema_corpo(slug_perfil=None, texto_bruto=None):
    if texto_bruto is not None:
        return _montar_texto(texto_bruto) + "\n\n"

    from jarvis.nucleo import perfis

    slug = slug_perfil or perfis.SLUG_PADRAO

    return _montar_texto(
        perfis.preparar_chamada(slug)["prompt_bruto"]
    ) + "\n\n"


def contexto_data_hora():
    return (
        "Data e hora local atual: "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}. "
    )


def bloco_autenticacao():
    return _carregar_prosa("geral/autenticacao.md")


CRIACAO_PERFIL = _carregar_arquivo("geral/criacao_perfil.md")
