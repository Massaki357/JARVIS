# Orquestra a confirmação (voz + notificação) de um comando que não
# está na whitelist — estruturalmente inspirado no mesmo padrão já
# usado em jarvis/pacotes/rede_jarvis/permissoes.py (um pedido pendente por vez,
# dois canais de resposta, timeout com negação por segurança), mas
# implementado de forma independente aqui: admin_terminal não importa
# nada de rede_jarvis (ver nota em notificacoes.py e em CLAUDE.md).
#
# Diferença importante em relação a jarvis/pacotes/rede_jarvis/permissoes.py: aqui a
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
import time

from . import config, executor, notificacoes

_pendente = None
_lock = threading.Lock()

# Guarda o resultado do ÚLTIMO pedido resolvido (por qualquer canal —
# voz ou notificação), por um tempo curto. BUG REAL relatado pelo
# usuário e corrigido aqui: como voz e notificação são disparadas em
# paralelo pelo mesmo pedido (ver solicitar_confirmacao), é comum o
# usuário clicar "Permitir" na notificação E TAMBÉM responder por voz
# (comportamento humano natural — as duas coisas parecem a mesma
# ação). Um dos dois canais perde a corrida (_tomar_pendente já
# resolvido) — sem este cache, responder_confirmacao_por_voz só tinha
# como dizer "não havia nenhum comando pendente", que soa como se nada
# tivesse acontecido, quando na verdade o comando já rodou (com
# sucesso ou falha) pelo outro canal. Com o cache, o canal que perdeu
# a corrida ainda consegue reportar o resultado real ao usuário, em
# vez de um beco sem saída confuso.
_ultimo_resolvido = None
_TTL_ULTIMO_RESOLVIDO_SEGUNDOS = 120


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


# Guarda o texto de resultado do último pedido resolvido, com
# timestamp — ver o comentário de _ultimo_resolvido, no topo do
# arquivo, pra o motivo desse cache existir.
def _registrar_ultimo_resolvido(resultado_texto):
    global _ultimo_resolvido

    with _lock:
        _ultimo_resolvido = {
            "resultado": resultado_texto,
            "resolvido_em": time.monotonic(),
        }


# Devolve o resultado do último pedido resolvido, só se ainda estiver
# dentro de _TTL_ULTIMO_RESOLVIDO_SEGUNDOS — evita responder com um
# resultado velho demais pra fazer sentido como resposta a uma
# pergunta atual.
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
