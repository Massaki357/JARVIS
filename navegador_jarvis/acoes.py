# Ações de navegador expostas pro despacho de tools — todas síncronas
# (mesma convenção do resto do projeto: despachar() é síncrona,
# rodada via asyncio.to_thread por quem chama) e nunca lançam exceção,
# sempre devolvem uma string pronta pra o jarvis falar.
import re
import urllib.parse

from . import sessao

# Regex pra decidir se um texto "parece" um endereço de site — exige
# um domínio no formato palavra.tld (ex: "google.com",
# "mercadolivre.com.br"), sem espaço nenhum no meio. Qualquer coisa
# que não bata (frases, nomes de site sem o domínio, ex: "mercado
# livre") é tratada como termo de busca — REGRA ESCOLHIDA
# deliberadamente simples: tentar adivinhar o domínio de uma marca a
# partir do nome falado (ex: "mercado livre" -> mercadolivre.com.br)
# seria uma lista de mapeamento manual frágil, que quebra pra
# qualquer site não cadastrado; uma busca no Google sempre funciona
# como fallback razoável.
_PADRAO_URL = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+"
    r"(/\S*)?$",
    re.IGNORECASE,
)


def _resolver_destino(url_ou_termo):
    texto = url_ou_termo.strip()

    if texto.startswith("http://") or texto.startswith("https://"):
        return texto

    if " " not in texto and _PADRAO_URL.match(texto):
        return "https://" + texto

    return (
        "https://www.google.com/search?q="
        + urllib.parse.quote(texto)
    )


async def _acao_abrir_site(pagina, destino):
    await pagina.goto(
        destino,
        wait_until="domcontentloaded",
    )

    return f"Site aberto: {pagina.url}"


def abrir_site(url_ou_termo):
    url_ou_termo = (url_ou_termo or "").strip()

    if not url_ou_termo:
        return "Nenhum site ou termo foi informado."

    destino = _resolver_destino(url_ou_termo)

    try:
        return sessao.executar_na_pagina(
            lambda pagina: _acao_abrir_site(pagina, destino)
        )

    except Exception as erro:
        return f"Não consegui abrir o site: {erro}"


# CONFIRMADO AO VIVO antes de implementar (a estrutura de classes CSS
# do YouTube muda com frequência — nunca hardcode sem checar): página
# de busca real do YouTube inspecionada com Playwright, testando vários
# seletores candidatos. 'a#video-title' bateu exatamente com a
# contagem de vídeos reais da página (19 elementos, mesma contagem de
# 'ytd-video-renderer a#video-title' e 'ytd-item-section-renderer
# ytd-video-renderer') e cada um tinha um href real '/watch?v=...' —
# ao contrário de 'a#thumbnail', que também pega elementos de outras
# seções (21 elementos). .first() testado clicando de verdade: navega
# pro vídeo, o player carrega e a música começa a tocar sozinha
# (confirmado lendo video.paused via JS depois do clique).
_SELETOR_PRIMEIRO_RESULTADO = "a#video-title"


async def _acao_tocar_musica(pagina, consulta):
    url_busca = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote(consulta)
    )

    await pagina.goto(
        url_busca,
        wait_until="domcontentloaded",
    )

    primeiro_resultado = pagina.locator(
        _SELETOR_PRIMEIRO_RESULTADO
    ).first

    await primeiro_resultado.wait_for(
        state="visible",
        timeout=15000,
    )

    await primeiro_resultado.click()

    # Aguarda o player carregar antes de considerar a ação concluída
    # — confirmado ao vivo que, nesse ponto, o vídeo já está de fato
    # tocando (video.paused == False).
    await pagina.wait_for_selector(
        "video",
        timeout=15000,
    )

    await pagina.wait_for_timeout(1500)

    titulo = await pagina.title()

    return f"Tocando no YouTube: {titulo}"


def tocar_musica_youtube(consulta):
    consulta = (consulta or "").strip()

    if not consulta:
        return "Nenhuma música ou termo de busca foi informado."

    try:
        return sessao.executar_na_pagina(
            lambda pagina: _acao_tocar_musica(pagina, consulta)
        )

    except Exception as erro:
        return f"Não consegui tocar a música: {erro}"


# Devolve o elemento <video> da página, ou None se não houver nenhum
# (a página não é uma página de vídeo — ex: o usuário abriu outro
# site depois de tocar uma música, ou nunca tocou nada).
async def _obter_video(pagina):
    if await pagina.locator("video").count() == 0:
        return None

    return pagina.locator("video").first


# Usa a tecla "k" do player do YouTube (atalho estável de
# play/pause — preferida a clicar num botão específico da interface,
# cuja posição/classe muda com mais frequência que atalhos de
# teclado), mas de forma DIRECIONAL, não um toggle cego: lê
# video.paused primeiro (propriedade padrão do HTMLMediaElement,
# nunca muda de nome/posição) e só aperta "k" se o estado realmente
# precisar mudar — evita que "pausar" já pausado acabe retomando por
# engano, e vice-versa.
async def _acao_pausar(pagina):
    video = await _obter_video(pagina)

    if video is None:
        return None

    se_esta_pausado = await pagina.evaluate(
        "el => el.paused",
        await video.element_handle(),
    )

    if se_esta_pausado:
        return "A música já estava pausada."

    await pagina.keyboard.press("k")
    await pagina.wait_for_timeout(300)

    return "Música pausada."


async def _acao_retomar(pagina):
    video = await _obter_video(pagina)

    if video is None:
        return None

    se_esta_pausado = await pagina.evaluate(
        "el => el.paused",
        await video.element_handle(),
    )

    if not se_esta_pausado:
        return "A música já estava tocando."

    await pagina.keyboard.press("k")
    await pagina.wait_for_timeout(300)

    return "Música retomada."


def pausar_musica():
    try:
        resultado = sessao.executar_se_pagina_existente(
            _acao_pausar
        )

    except Exception as erro:
        return f"Não consegui pausar a música: {erro}"

    if resultado is None:
        return "Não há nada tocando agora."

    return resultado


def retomar_musica():
    try:
        resultado = sessao.executar_se_pagina_existente(
            _acao_retomar
        )

    except Exception as erro:
        return f"Não consegui retomar a música: {erro}"

    if resultado is None:
        return "Não há nada tocando agora."

    return resultado


def fechar_navegador():
    try:
        sessao.fechar()

    except Exception as erro:
        return f"Não consegui fechar o navegador: {erro}"

    return "Navegador fechado."
