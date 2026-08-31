# Sessão de navegador persistente — mantém UM browser/contexto/página
# do Playwright abertos entre chamadas, pra "pausar a música" agir na
# MESMA aba onde ela foi colocada, em vez de abrir um navegador novo
# (sem contexto nenhum) a cada comando.
#
# API assíncrona do Playwright (playwright.async_api), não a síncrona
# — decisão do usuário, e também a única viável aqui: a API síncrona
# roda sua própria thread/loop internos e prende os objetos
# browser/context/page à thread que os criou; como despachar() (o
# ponto de entrada padrão do projeto) roda numa thread genérica do
# pool do asyncio.to_thread, que pode variar entre chamadas, uma
# sessão síncrona persistente quebraria na segunda chamada se caísse
# numa thread diferente da primeira. Por isso o Playwright roda numa
# thread de fundo DEDICADA, com seu próprio loop asyncio — mesmo
# padrão já usado em discord_jarvis/cliente.py (discord.py) e
# rede_jarvis/visualizacao_remota.py (loop dedicado +
# run_coroutine_threadsafe como ponte pra chamadas síncronas).
import asyncio
import threading

from playwright.async_api import Error as ErroPlaywright
from playwright.async_api import async_playwright

from . import config

_thread = None
_loop = None
_loop_pronto = threading.Event()
_lock_thread = threading.Lock()

# Só acessados de dentro do loop dedicado (_loop) — nunca direto de
# outra thread, sempre através de _rodar()/executar_na_pagina().
_playwright = None
_navegador = None
_contexto = None
_pagina = None


def _rodar_loop_do_navegador():
    global _loop

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_pronto.set()

    _loop.run_forever()


# Sobe a thread de fundo com o loop dedicado, se ainda não estiver de
# pé — idempotente. Ao contrário de rede_jarvis/discord_jarvis (que
# sobem a conexão deles a partir do __init__ do worker, pra ficarem de
# pé mesmo fora de uma chamada), esta thread só é criada sob demanda,
# na primeira ação de navegador pedida — não faz sentido abrir um
# Chromium antes de qualquer pedido.
def _garantir_thread():
    global _thread

    with _lock_thread:
        if _thread is not None and _thread.is_alive():
            return

        _loop_pronto.clear()

        _thread = threading.Thread(
            target=_rodar_loop_do_navegador,
            daemon=True,
        )

        _thread.start()

        _loop_pronto.wait(
            timeout=5
        )


# Roda uma corrotina no loop do navegador a partir de qualquer thread
# (despachar() roda numa thread de fundo, via asyncio.to_thread) e
# espera o resultado — mesma técnica de
# discord_jarvis/cliente.py:_rodar_no_loop_do_bot.
def _rodar(corrotina, timeout):
    _garantir_thread()

    future = asyncio.run_coroutine_threadsafe(
        corrotina,
        _loop,
    )

    return future.result(timeout=timeout)


# Fecha tudo silenciosamente (ignora erros — objetos já podem estar
# mortos) e zera as referências. Chamada tanto pra encerrar a sessão
# de propósito (fechar_navegador) quanto pra limpar uma sessão que
# caiu sozinha antes de abrir uma nova (ver _obter_pagina_async).
async def _fechar_tudo_async():
    global _playwright, _navegador, _contexto, _pagina

    if _contexto is not None:
        try:
            await _contexto.close()

        except Exception:
            pass

    if _navegador is not None:
        try:
            await _navegador.close()

        except Exception:
            pass

    if _playwright is not None:
        try:
            await _playwright.stop()

        except Exception:
            pass

    _playwright = None
    _navegador = None
    _contexto = None
    _pagina = None


# Devolve a página ativa, reaproveitando a sessão existente se ela
# ainda estiver viva. Se não houver sessão, ou se a página/navegador
# tiver caído/fechado (ex: o usuário fechou a janela na mão), limpa
# tudo e abre uma sessão nova do zero — nunca lança erro por causa de
# uma sessão morta, sempre se recupera sozinha.
async def _obter_pagina_async():
    global _playwright, _navegador, _contexto, _pagina

    if _pagina is not None:
        try:
            if not _pagina.is_closed():
                return _pagina

        except Exception:
            pass

    await _fechar_tudo_async()

    _playwright = await async_playwright().start()

    # headless=False de propósito — o navegador precisa ficar
    # visível e com saída de áudio de verdade pra tocar música (modo
    # headless não tem isso de forma simples/confiável).
    _navegador = await _playwright.chromium.launch(
        headless=False
    )

    _contexto = await _navegador.new_context()
    _pagina = await _contexto.new_page()

    return _pagina


# Devolve a página ativa SE já existir uma sessão viva, sem criar uma
# nova — usado por pausar/retomar, que não fazem sentido abrindo um
# navegador do zero só pra descobrir que não há nada tocando.
async def _pagina_existente_async():
    if _pagina is None:
        return None

    try:
        if _pagina.is_closed():
            return None

    except Exception:
        return None

    return _pagina


# Ponto de entrada usado por navegador_jarvis/acoes.py pra qualquer
# ação que PODE precisar abrir a sessão (abrir_site,
# tocar_musica_youtube): obtém a página (abrindo sessão nova se
# preciso), roda func_async(pagina), e se a ação falhar com um erro do
# Playwright (sinal de que a página/navegador morreu NO MEIO da ação —
# ex: o usuário fechou a janela enquanto isso rodava), reabre a sessão
# do zero e tenta mais uma vez, antes de desistir de vez.
def executar_na_pagina(func_async, timeout=None):
    timeout = timeout or config.TIMEOUT_ACAO_SEGUNDOS

    async def _com_retentativa():
        pagina = await _obter_pagina_async()

        try:
            return await func_async(pagina)

        except ErroPlaywright:
            pagina = await _obter_pagina_async()
            return await func_async(pagina)

    return _rodar(
        _com_retentativa(),
        timeout=max(
            timeout,
            config.TIMEOUT_INICIO_SEGUNDOS,
        ),
    )


# Ponto de entrada usado por pausar_musica/retomar_musica: só roda
# func_async se já existir uma sessão viva — devolve None sem criar
# nada se não houver (o chamador interpreta None como "não há nada
# tocando agora").
def executar_se_pagina_existente(func_async, timeout=None):
    timeout = timeout or config.TIMEOUT_ACAO_SEGUNDOS

    async def _wrapper():
        pagina = await _pagina_existente_async()

        if pagina is None:
            return None

        try:
            return await func_async(pagina)

        except ErroPlaywright:
            return None

    return _rodar(
        _wrapper(),
        timeout=timeout,
    )


# Encerra a sessão do Playwright de forma limpa (ver
# navegador_jarvis/acoes.py:fechar_navegador).
def fechar():
    _rodar(
        _fechar_tudo_async(),
        timeout=config.TIMEOUT_ACAO_SEGUNDOS,
    )
