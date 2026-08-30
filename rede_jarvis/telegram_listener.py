from . import comandos, config, permissoes, telegram_client

import json
import threading
import time
import uuid

# Correlaciona pedidos enviados por esta máquina (comando ou consulta
# de service account) com a resposta recebida, por id_pedido.
# Cada valor é (threading.Event, dict com "sucesso"/"resultado").
_RESPOSTAS_PENDENTES = {}
_LOCK_RESPOSTAS = threading.Lock()

_callback_falar = None
_callback_frame_remoto = None

_offset_atual = 0
_rodando = False
_lock_rodando = threading.Lock()


# Registra os callbacks usados para o Jarvis "falar" por voz e para
# injetar frames de visualização remota na sessão Live local. É
# chamada sempre que rede_jarvis.iniciar_rede_jarvis() roda (a cada
# nova chamada de voz), para nunca ficar com callbacks apontando para
# um GeminiLiveWorker de uma chamada já encerrada.
def configurar_callbacks(callback_falar, callback_frame_remoto):
    global _callback_falar, _callback_frame_remoto

    _callback_falar = callback_falar
    _callback_frame_remoto = callback_frame_remoto


# Inicia a thread de polling do Telegram. Idempotente: chamadas
# repetidas (uma por chamada de voz iniciada) não criam uma segunda
# thread.
def iniciar_em_thread():
    global _rodando

    with _lock_rodando:
        if _rodando:
            return

        _rodando = True

    threading.Thread(
        target=_loop_principal,
        daemon=True,
    ).start()


# Faz polling do bot compartilhado. AVISO: como várias máquinas
# compartilham o mesmo token de bot, chamadas concorrentes de
# getUpdates podem conflitar entre si — o Telegram só permite um
# consumidor de getUpdates de cada vez por bot. Por isso usamos um
# timeout de long-polling curto (2s) e uma pequena pausa entre
# chamadas, o que reduz bastante a janela de conflito, mas não a
# elimina por completo. Para poucas máquinas com tráfego baixo (o
# cenário deste projeto) isso funciona na prática; um relay/servidor
# central resolveria de vez, mas fica fora do escopo "sem VPN, só o
# bot" pedido.
def _loop_principal():
    global _offset_atual

    while True:
        try:
            atualizacoes = telegram_client.obter_atualizacoes(
                offset=_offset_atual,
                timeout_segundos=2,
            )

            for atualizacao in atualizacoes:
                _offset_atual = atualizacao["update_id"] + 1

                _processar_atualizacao(atualizacao)

        except Exception as erro:
            print(
                f"[rede_jarvis] Erro no listener do Telegram: {erro}"
            )

        time.sleep(1)


def _processar_atualizacao(atualizacao):
    mensagem = atualizacao.get("message")

    if not mensagem:
        return

    if "photo" in mensagem:
        _processar_foto(mensagem)
        return

    if "document" in mensagem:
        _processar_documento(mensagem)
        return

    texto = mensagem.get("text")

    if texto:
        _processar_texto(texto)


# Valida o token compartilhado e o destino de um envelope JSON.
# Mensagens sem o token correto, malformadas, ou destinadas a outra
# máquina são descartadas silenciosamente — não confirmamos a um
# atacante que o bot existe nem respondemos a mensagens que não são
# para esta máquina.
def _carregar_envelope(texto):
    try:
        envelope = json.loads(texto)

    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(envelope, dict):
        return None

    if envelope.get("token") != config.TOKEN_REDE_JARVIS:
        return None

    if envelope.get("destino") not in (config.NOME_MAQUINA, "todos"):
        return None

    return envelope


def _processar_texto(texto):
    envelope = _carregar_envelope(texto)

    if not envelope:
        return

    tipo = envelope.get("tipo")

    if tipo == "comando":
        _processar_comando(envelope)

    elif tipo == "resposta":
        _processar_resposta(envelope)

    elif tipo == "consulta_service_account":
        _responder_consulta_service_account(envelope)

    elif tipo == "arquivo_drive":
        _processar_arquivo_drive(envelope)


def _registrar_log(origem, comando):
    try:
        with open(
            config.ARQUIVO_LOG,
            "a",
            encoding="utf-8",
        ) as arquivo:
            momento = time.strftime("%Y-%m-%d %H:%M:%S")

            arquivo.write(
                f"{momento} | de={origem} | comando={comando}\n"
            )

    except OSError:
        pass


def _processar_comando(envelope):
    origem = envelope.get("origem", "desconhecido")
    comando = envelope.get("comando", "")
    argumentos = envelope.get("argumentos") or {}
    id_pedido = envelope.get("id_pedido")

    _registrar_log(origem, comando)

    def _executar():
        permitido = permissoes.solicitar_permissao(
            origem,
            comando,
            _callback_falar,
        )

        if not permitido:
            _responder(
                origem,
                id_pedido,
                sucesso=False,
                resultado="Comando negado.",
            )

            return

        resultado = comandos.executar_comando(
            comando,
            origem,
            argumentos,
        )

        _responder(
            origem,
            id_pedido,
            sucesso=True,
            resultado=resultado,
        )

    threading.Thread(
        target=_executar,
        daemon=True,
    ).start()


def _responder(destino, id_pedido, sucesso, resultado):
    envelope_resposta = json.dumps(
        {
            "token": config.TOKEN_REDE_JARVIS,
            "origem": config.NOME_MAQUINA,
            "destino": destino,
            "tipo": "resposta",
            "id_pedido": id_pedido,
            "sucesso": sucesso,
            "resultado": resultado,
        }
    )

    telegram_client.enviar_mensagem(
        config.TELEGRAM_CHAT_ID,
        envelope_resposta,
    )


def _processar_resposta(envelope):
    id_pedido = envelope.get("id_pedido")

    with _LOCK_RESPOSTAS:
        pendente = _RESPOSTAS_PENDENTES.get(id_pedido)

    if not pendente:
        return

    evento, container = pendente

    container["sucesso"] = envelope.get("sucesso")
    container["resultado"] = envelope.get("resultado")

    evento.set()


def _responder_consulta_service_account(envelope):
    # Import tardio para evitar import circular (transferencia_arquivos
    # importa este módulo para pedir o client_email da máquina destino).
    from . import transferencia_arquivos

    email = transferencia_arquivos.obter_client_email_local()

    _responder(
        envelope.get("origem", "desconhecido"),
        envelope.get("id_pedido"),
        sucesso=bool(email),
        resultado=(
            email
            or "Service Account não configurada nesta máquina."
        ),
    )


def _processar_arquivo_drive(envelope):
    from . import transferencia_arquivos

    threading.Thread(
        target=transferencia_arquivos.baixar_e_receber_arquivo_drive,
        args=(
            envelope.get("origem", "desconhecido"),
            envelope.get("id_arquivo_drive"),
            envelope.get("nome_arquivo", "arquivo_recebido"),
        ),
        daemon=True,
    ).start()


def _processar_foto(mensagem):
    legenda = mensagem.get("caption", "")
    envelope = _carregar_envelope(legenda)

    if not envelope or envelope.get("tipo") != "frame_visualizacao":
        return

    fotos = mensagem.get("photo") or []

    if not fotos:
        return

    # A API do Telegram retorna várias resoluções da mesma foto; a
    # maior é sempre o último item da lista.
    file_id = fotos[-1]["file_id"]

    frame_bytes = telegram_client.baixar_arquivo(file_id)

    if frame_bytes and _callback_frame_remoto:
        _callback_frame_remoto(
            frame_bytes,
            envelope.get("origem", "desconhecido"),
        )


def _processar_documento(mensagem):
    legenda = mensagem.get("caption", "")
    envelope = _carregar_envelope(legenda)

    if not envelope:
        return

    documento = mensagem.get("document") or {}
    file_id = documento.get("file_id")
    nome_arquivo = documento.get("file_name", "arquivo_recebido")

    if not file_id:
        return

    conteudo = telegram_client.baixar_arquivo(file_id)

    if conteudo is None:
        return

    from . import transferencia_arquivos

    transferencia_arquivos.receber_arquivo(
        envelope.get("origem", "desconhecido"),
        nome_arquivo,
        conteudo,
    )


# Envia um envelope e aguarda a resposta correlacionada por
# id_pedido (usado tanto para comandos remotos quanto para a consulta
# de client_email do Google Drive).
def _enviar_e_aguardar(envelope, timeout):
    id_pedido = envelope["id_pedido"]
    evento = threading.Event()
    container = {}

    with _LOCK_RESPOSTAS:
        _RESPOSTAS_PENDENTES[id_pedido] = (evento, container)

    enviado = telegram_client.enviar_mensagem(
        config.TELEGRAM_CHAT_ID,
        json.dumps(envelope),
    )

    if not enviado:
        with _LOCK_RESPOSTAS:
            _RESPOSTAS_PENDENTES.pop(id_pedido, None)

        return None

    recebido_a_tempo = evento.wait(timeout=timeout)

    with _LOCK_RESPOSTAS:
        _RESPOSTAS_PENDENTES.pop(id_pedido, None)

    return container if recebido_a_tempo else None


# Envia um comando remoto para maquina_destino e aguarda a resposta
# (usado pela tool enviar_comando_remoto, via
# rede_jarvis.enviar_comando_remoto).
def enviar_comando(maquina_destino, comando, argumentos, timeout=None):
    envelope = {
        "token": config.TOKEN_REDE_JARVIS,
        "origem": config.NOME_MAQUINA,
        "destino": maquina_destino,
        "tipo": "comando",
        "id_pedido": str(uuid.uuid4()),
        "comando": comando,
        "argumentos": argumentos or {},
    }

    container = _enviar_e_aguardar(
        envelope,
        timeout or config.TIMEOUT_RESPOSTA_COMANDO,
    )

    if container is None:
        return f"A máquina '{maquina_destino}' não respondeu a tempo."

    return str(
        container.get(
            "resultado",
            "Comando executado, sem detalhes retornados.",
        )
    )


# Pergunta a outra máquina qual é o client_email da Service Account
# dela, usado antes de compartilhar um arquivo grande via Drive.
def consultar_client_email(maquina_destino, timeout=None):
    envelope = {
        "token": config.TOKEN_REDE_JARVIS,
        "origem": config.NOME_MAQUINA,
        "destino": maquina_destino,
        "tipo": "consulta_service_account",
        "id_pedido": str(uuid.uuid4()),
    }

    container = _enviar_e_aguardar(
        envelope,
        timeout or config.TIMEOUT_CONSULTA_SERVICE_ACCOUNT,
    )

    if container is None or not container.get("sucesso"):
        return None

    return container.get("resultado")
