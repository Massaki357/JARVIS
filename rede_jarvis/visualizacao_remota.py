# Reaproveita a classe de captura contínua já existente para a
# visualização local — a única diferença aqui é o destino de cada
# frame (MQTT em vez de session.send_realtime_input direto).
from vision.monitor_continuo import MonitorTelaContinuo

from . import config, mqtt_client

import asyncio
import threading

# Guarda as sessões de visualização remota ativas nesta máquina,
# indexadas pela máquina de origem que pediu (só permite uma
# visualização remota ativa por máquina solicitante de cada vez).
# Cada entrada é {"monitor": MonitorTelaContinuo, "loop": event loop}.
_SESSOES_ATIVAS = {}
_LOCK_SESSOES = threading.Lock()


# Inicia a captura contínua da tela local e publica cada frame no
# tópico de frames do MQTT, com token/origem/destino/id_sessao nas
# propriedades da mensagem, para a máquina que pediu conseguir
# reconhecer os frames recebidos.
#
# Roda em uma thread própria, com seu próprio loop asyncio — decoupled
# de propósito do loop (transiente, só existe durante uma chamada) do
# GeminiLiveWorker, já que a visualização remota deve continuar
# funcionando independente de haver uma chamada de voz ativa nesta
# máquina.
def iniciar(origem, id_sessao):
    with _LOCK_SESSOES:
        if origem in _SESSOES_ATIVAS:
            return (
                "Já existe uma visualização remota ativa para essa "
                "máquina."
            )

        # Reserva o slot antes de iniciar a thread, para evitar duas
        # chamadas simultâneas criarem duas sessões para a mesma origem.
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
        # mqtt_client.publicar_frame é síncrona e thread-safe (o
        # paho-mqtt cuida da própria thread de rede internamente) —
        # roda numa thread comum pra não bloquear este loop enquanto
        # a mensagem é entregue ao broker.
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

    # Mantém o loop vivo para a tarefa de captura do monitor continuar
    # avançando; é interrompido por parar() ou pelo timeout automático
    # (callback_encerrado chama loop.stop()).
    loop.run_forever()
    loop.close()


# Interrompe a visualização remota ativa para a máquina de origem
# informada, caso exista.
def parar(origem):
    with _LOCK_SESSOES:
        sessao = _SESSOES_ATIVAS.get(origem)

    if not sessao or "monitor" not in sessao:
        return "Não há visualização remota ativa para essa máquina."

    monitor = sessao["monitor"]
    loop = sessao["loop"]

    # monitor.parar() não deve chamar loop.stop() por conta própria:
    # se a última linha da corrotina agendada via
    # run_coroutine_threadsafe parar o loop, o callback interno que
    # propaga o resultado para o future (usado por futuro.result()
    # abaixo) pode nunca chegar a rodar, e a chamada trava até o
    # timeout mesmo com tudo tendo funcionado. Por isso o loop só é
    # parado depois, com call_soon_threadsafe — sem essa disputa.
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
