import threading

from . import config, notificacoes

# Guarda o "resolvedor" (callback) do pedido de permissão que está
# aguardando confirmação por voz no momento. Como só existe uma
# chamada de voz ativa por vez no ALFRED, só há sentido em ter um
# pedido pendente de confirmação por voz por vez — se um segundo
# pedido chegar antes do primeiro ser resolvido, ele passa a ser o
# único que a tool responder_permissao_remota consegue resolver por
# voz (o primeiro ainda pode ser resolvido pela notificação).
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


# Chamado pelo dispatch da tool responder_permissao_remota quando o
# usuário responde por voz a um pedido de permissão anunciado.
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


# Bloqueia (nesta thread de background do listener) até o comando
# remoto ser permitido, negado, ou até estourar o timeout — usando o
# primeiro canal que responder entre a notificação do Windows e a
# confirmação por voz. Timeout = negado por padrão (fail-safe).
def solicitar_permissao(origem, comando, callback_falar=None):
    if not config.PEDIR_PERMISSAO:
        return True

    resultado = {"valor": None}
    evento = threading.Event()

    def _resolver(concedido):
        # Só o primeiro canal a responder conta; ignora respostas
        # atrasadas do outro canal.
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
