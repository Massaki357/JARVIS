from . import config, permissoes, telegram_listener, transferencia_arquivos


# Ponto de entrada único do pacote. Sobe o listener do Telegram em
# background (idempotente — chamadas repetidas não iniciam uma
# segunda thread) e (re)registra os callbacks usados para o Jarvis
# "falar" algo por voz e para injetar frames de visualização remota
# na sessão Live local.
#
# Deve ser chamada a partir da thread principal (GUI) — prepara
# também a ponte usada pelo diálogo de "salvar arquivo recebido"
# (ver transferencia_arquivos.preparar_ponte_gui).
def iniciar_rede_jarvis(callback_falar=None, callback_frame_remoto=None):
    transferencia_arquivos.preparar_ponte_gui()

    telegram_listener.configurar_callbacks(
        callback_falar,
        callback_frame_remoto,
    )

    telegram_listener.iniciar_em_thread()


# Usado pela tool de voz enviar_comando_remoto em
# gemini/live_client_basic.py.
#
# "enviar_arquivo" é tratado localmente: é a própria máquina que
# envia um arquivo que ela tem, não um comando para a máquina remota
# executar. Todos os outros comandos são de fato despachados pelo
# Telegram para maquina_destino executar e responder.
def enviar_comando_remoto(maquina_destino, comando, argumentos=None):
    if comando == "enviar_arquivo":
        argumentos_com_destino = dict(argumentos or {})
        argumentos_com_destino.setdefault(
            "maquina_destino",
            maquina_destino,
        )

        return transferencia_arquivos.enviar_arquivo(
            config.NOME_MAQUINA,
            argumentos_com_destino,
        )

    return telegram_listener.enviar_comando(
        maquina_destino,
        comando,
        argumentos,
    )


# Usado pela tool de voz responder_permissao_remota em
# gemini/live_client_basic.py.
def responder_permissao_por_voz(concedido):
    return permissoes.responder_permissao_por_voz(concedido)
