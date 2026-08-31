# Orquestra a confirmação (voz + notificação) de um comando que não
# está na whitelist — estruturalmente inspirado no mesmo padrão já
# usado em rede_jarvis/permissoes.py (um pedido pendente por vez,
# dois canais de resposta, timeout com negação por segurança), mas
# implementado de forma independente aqui: admin_terminal não importa
# nada de rede_jarvis (ver nota em notificacoes.py e em CLAUDE.md).
#
# Diferença importante em relação a rede_jarvis/permissoes.py: aqui a
# função NUNCA bloqueia. O pedido original (executar_comando_admin)
# já retorna na hora, pedindo pro próprio Gemini perguntar ao usuário
# por voz — isso evita empurrar uma nova mensagem espontânea pra
# sessão Live enquanto uma tool_call ainda está pendente de resposta
# (o padrão de rede_jarvis funciona porque o pedido remoto chega numa
# thread MQTT totalmente fora do fluxo da conversa; aqui o pedido já
# nasce dentro da conversa atual). Só quando a resposta vem pelo
# clique da notificação — que acontece numa thread solta, sem
# nenhuma tool_call esperando — é que o resultado precisa ser
# anunciado por voz de forma espontânea (callback_falar).
import threading

from . import config, executor, notificacoes

_pendente = None
_lock = threading.Lock()


# Registra um novo pedido pendente e dispara a notificação + o timer
# de timeout. Não bloqueia. callback_falar é usado só se a resposta
# vier pela notificação (ver _resolver_por_notificacao) — quando a
# resposta vem por voz (confirmar_comando_admin), o resultado é
# devolvido direto como retorno da tool, sem precisar de callback.
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
        # Só pode existir um pedido pendente por vez — se um novo
        # chegou antes do anterior ser resolvido, o anterior nunca
        # mais pode ser confirmado (nega por segurança quando o timer
        # dele disparar; aqui só desarmamos o timer pra não disparar
        # duas notificações de resultado).
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


# Chamado a partir de despachar("confirmar_comando_admin", ...) — já
# roda dentro de uma tool_call normal do Gemini esperando resposta,
# então o resultado é devolvido direto como string, sem precisar de
# callback_falar.
def responder_confirmacao_por_voz(confirmado):
    estado = _tomar_pendente()

    if not estado:
        return (
            "Não havia nenhum comando administrativo aguardando "
            "confirmação."
        )

    return executor.executar_comando_confirmado(
        estado["comando"],
        confirmado,
        estado["execucao_longa"],
        origem="voz",
    )


# Chamado numa thread de fundo (clique no botão da notificação, ou
# estouro do timeout) — nunca a partir de uma tool_call, por isso o
# resultado precisa ser anunciado espontaneamente por voz.
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

    callback_falar = estado.get("callback_falar")

    if callback_falar:
        try:
            callback_falar(texto_resultado)

        except Exception as erro:
            print(
                "[admin_terminal] Falha ao anunciar resultado por "
                f"voz: {erro}"
            )


# Marca o pedido pendente atual como resolvido e o retorna — garante
# que só o primeiro canal a responder (voz, notificação ou timeout)
# tem efeito. Se estado_esperado for informado, só toma se ainda for
# o pedido pendente atual (evita resolver duas vezes um pedido já
# substituído por um mais novo).
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
