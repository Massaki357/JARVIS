import threading

from . import config, notificacoes

_resolvedor_voz_atual = None
_lock_voz = threading.Lock()


def _registrar_pedido_voz(resolver):
    global _resolvedor_voz_atual

    with _lock_voz:
        _resolvedor_voz_atual = resolver


def _liberar_pedido_voz(resolver_esperado):
    global _resolvedor_voz_atual

    with _lock_voz:
        if _resolvedor_voz_atual is resolver_esperado:
            _resolvedor_voz_atual = None


def responder_permissao_por_voz(concedido):
    with _lock_voz:
        resolver = _resolvedor_voz_atual

    if not resolver:
        return (
            "Não havia nenhum pedido de permissão remota aguardando "
            "resposta por voz."
        )

    resolver(bool(concedido))

    return "Resposta registrada."


def solicitar_permissao(origem, comando, callback_falar=None):
    if not config.PEDIR_PERMISSAO:
        return True

    resultado = {"valor": None}
    evento = threading.Event()

    def _resolver(concedido):
        if resultado["valor"] is None:
            resultado["valor"] = concedido
            evento.set()

    notificacoes.notificar_pedido_permissao(
        titulo=f"Pedido remoto de {origem}",
        mensagem=f"Comando: {comando}. Permitir?",
        ao_responder=_resolver,
    )

    if callback_falar:
        _registrar_pedido_voz(_resolver)

        try:
            callback_falar(
                f"Pedido remoto de {origem} para {comando}. "
                "Diga permitir ou negar."
            )

        except Exception as erro:
            print(
                f"[rede_jarvis] Falha ao anunciar pedido por voz: {erro}"
            )

    resolvido_a_tempo = evento.wait(
        timeout=config.TIMEOUT_PERMISSAO
    )

    if callback_falar:
        _liberar_pedido_voz(_resolver)

    if not resolvido_a_tempo:
        return False

    return bool(resultado["valor"])
