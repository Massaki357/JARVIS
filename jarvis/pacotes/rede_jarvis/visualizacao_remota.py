from jarvis.servicos.visao.monitor_continuo import MonitorTelaContinuo

from . import config, mqtt_client

import asyncio
import threading

_SESSOES_ATIVAS = {}
_LOCK_SESSOES = threading.Lock()


def iniciar(origem, id_sessao):
    with _LOCK_SESSOES:
        if origem in _SESSOES_ATIVAS:
            return (
                "Já existe uma visualização remota ativa para essa "
                "máquina."
            )

        _SESSOES_ATIVAS[origem] = {}

    pronto = threading.Event()

    threading.Thread(
        target=_executar_thread,
        args=(origem, id_sessao, pronto),
        daemon=True,
    ).start()

    pronto.wait(timeout=5)

    return "Visualização remota iniciada."


def _executar_thread(origem, id_sessao, pronto):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _callback_frame(frame_bytes):
        await asyncio.to_thread(
            mqtt_client.publicar_frame,
            frame_bytes,
            config.NOME_MAQUINA,
            origem,
            id_sessao,
        )

    async def _callback_encerrado():
        with _LOCK_SESSOES:
            _SESSOES_ATIVAS.pop(origem, None)

        loop.stop()

    # Sem funcao_captura de propósito: monitor primário fixo (docs/rede_jarvis.md).
    monitor = MonitorTelaContinuo(
        callback_frame=_callback_frame,
        intervalo_segundos=config.INTERVALO_VISUALIZACAO_REMOTA,
        timeout_segundos=config.TIMEOUT_VISUALIZACAO_REMOTA,
        callback_encerrado=_callback_encerrado,
    )

    with _LOCK_SESSOES:
        _SESSOES_ATIVAS[origem] = {
            "monitor": monitor,
            "loop": loop,
        }

    loop.run_until_complete(
        monitor.iniciar()
    )

    pronto.set()

    loop.run_forever()
    loop.close()


def parar(origem):
    with _LOCK_SESSOES:
        sessao = _SESSOES_ATIVAS.get(origem)

    if not sessao or "monitor" not in sessao:
        return "Não há visualização remota ativa para essa máquina."

    monitor = sessao["monitor"]
    loop = sessao["loop"]

    futuro = asyncio.run_coroutine_threadsafe(
        monitor.parar(),
        loop,
    )

    try:
        futuro.result(timeout=5)

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao encerrar visualização remota: {erro}"
        )

    loop.call_soon_threadsafe(loop.stop)

    with _LOCK_SESSOES:
        _SESSOES_ATIVAS.pop(origem, None)

    return "Visualização remota encerrada."
