import threading
import time

from . import config, executor, notificacoes

_pendente = None
_lock = threading.Lock()

_ultimo_resolvido = None
_TTL_ULTIMO_RESOLVIDO_SEGUNDOS = 120


def solicitar_confirmacao(comando, motivo, execucao_longa, callback_falar):
    global _pendente

    with _lock:
        pendente_anterior = _pendente

        estado = {
            "comando": comando,
            "execucao_longa": execucao_longa,
            "callback_falar": callback_falar,
            "resolvido": False,
        }

        _pendente = estado

    if pendente_anterior is not None:
        pendente_anterior["timer"].cancel()
        pendente_anterior["resolvido"] = True

    def _ao_responder_notificacao(concedido):
        _resolver_por_notificacao(estado, concedido)

    notificacoes.notificar_pedido_confirmacao(
        titulo="Comando administrativo aguardando confirmação",
        mensagem=f"{motivo}\nComando: {comando}",
        ao_responder=_ao_responder_notificacao,
    )

    timer = threading.Timer(
        config.TIMEOUT_CONFIRMACAO_SEGUNDOS,
        lambda: _resolver_por_notificacao(estado, False),
    )
    timer.daemon = True
    timer.start()

    estado["timer"] = timer


def responder_confirmacao_por_voz(confirmado):
    estado = _tomar_pendente()

    if not estado:
        resultado_recente = _obter_ultimo_resolvido()

        if resultado_recente:
            return (
                "Esse comando já tinha sido respondido pela "
                "notificação do Windows antes da sua resposta por "
                f"voz chegar. Resultado: {resultado_recente}"
            )

        return (
            "Não havia nenhum comando administrativo aguardando "
            "confirmação."
        )

    resultado = executor.executar_comando_confirmado(
        estado["comando"],
        confirmado,
        estado["execucao_longa"],
        origem="voz",
    )

    _registrar_ultimo_resolvido(resultado)

    return resultado


def _resolver_por_notificacao(estado_esperado, confirmado):
    estado = _tomar_pendente(estado_esperado)

    if not estado:
        return

    texto_resultado = executor.executar_comando_confirmado(
        estado["comando"],
        confirmado,
        estado["execucao_longa"],
        origem="notificacao",
    )

    _registrar_ultimo_resolvido(texto_resultado)

    callback_falar = estado.get("callback_falar")

    if callback_falar:
        try:
            callback_falar(texto_resultado)

        except Exception as erro:
            print(
                "[admin_terminal] Falha ao anunciar resultado por "
                f"voz: {erro}"
            )


def _tomar_pendente(estado_esperado=None):
    global _pendente

    with _lock:
        estado = _pendente

        if not estado or estado["resolvido"]:
            return None

        if estado_esperado is not None and estado is not estado_esperado:
            return None

        estado["resolvido"] = True
        estado["timer"].cancel()

        if _pendente is estado:
            _pendente = None

        return estado


def _registrar_ultimo_resolvido(resultado_texto):
    global _ultimo_resolvido

    with _lock:
        _ultimo_resolvido = {
            "resultado": resultado_texto,
            "resolvido_em": time.monotonic(),
        }


def _obter_ultimo_resolvido():
    with _lock:
        if _ultimo_resolvido is None:
            return None

        if (
            time.monotonic() - _ultimo_resolvido["resolvido_em"]
            > _TTL_ULTIMO_RESOLVIDO_SEGUNDOS
        ):
            return None

        return _ultimo_resolvido["resultado"]
