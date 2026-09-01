from . import comandos, config, mqtt_client, permissoes

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

_rodando = False
_lock_rodando = threading.Lock()

# Máquinas conhecidas como online agora, a partir das mensagens
# retidas de presença (ver mqtt_client.publicar_presenca). Nome da
# máquina -> momento (time.time()) em que o "online" foi visto.
_MAQUINAS_ONLINE = {}
_LOCK_MAQUINAS = threading.Lock()


# Registra os callbacks usados para o Jarvis "falar" por voz e para
# injetar frames de visualização remota na sessão Live local. É
# chamada sempre que rede_jarvis.iniciar_rede_jarvis() roda (a cada
# nova chamada de voz), para nunca ficar com callbacks apontando para
# um GeminiLiveWorker de uma chamada já encerrada.
def configurar_callbacks(callback_falar, callback_frame_remoto):
    global _callback_falar, _callback_frame_remoto

    _callback_falar = callback_falar
    _callback_frame_remoto = callback_frame_remoto


# Conecta ao broker e inicia o loop de rede do paho-mqtt (que já roda
# em sua própria thread interna — loop_start() retorna na hora).
# Idempotente: chamadas repetidas (uma por chamada de voz iniciada)
# não conectam duas vezes.
def iniciar_em_thread():
    global _rodando

    with _lock_rodando:
        if _rodando:
            return

        _rodando = True

    cliente = mqtt_client.obter_cliente()

    cliente.on_connect = _ao_conectar
    cliente.on_message = _ao_receber_mensagem
    cliente.on_disconnect = _ao_desconectar

    try:
        cliente.connect(
            config.MQTT_HOST,
            config.MQTT_PORT,
            keepalive=60,
        )

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao conectar no broker MQTT: {erro}"
        )

        return

    cliente.loop_start()


def _ao_conectar(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(
            f"[rede_jarvis] Falha ao autenticar no broker MQTT: {reason_code}"
        )

        return

    print("[rede_jarvis] Conectado ao broker MQTT.")

    client.subscribe(mqtt_client.TOPICO_COMANDOS, qos=1)
    client.subscribe(mqtt_client.TOPICO_FRAMES, qos=0)
    client.subscribe(mqtt_client.TOPICO_ARQUIVOS, qos=1)

    # "+" é o coringa de um nível no MQTT: cobre o tópico de presença
    # de qualquer máquina (jarvis/presenca/<nome>). As mensagens
    # retidas de todo mundo chegam automaticamente logo após a
    # inscrição, sem precisar perguntar nada a ninguém.
    client.subscribe(
        mqtt_client.TOPICO_PRESENCA_PREFIXO + "+",
        qos=1,
    )

    mqtt_client.publicar_presenca("online")


def _ao_desconectar(client, userdata, flags, reason_code, properties):
    print(
        f"[rede_jarvis] Desconectado do broker MQTT ({reason_code}). "
        "O paho-mqtt tenta reconectar sozinho."
    )


def _ao_receber_mensagem(client, userdata, mensagem):
    try:
        if mensagem.topic == mqtt_client.TOPICO_COMANDOS:
            _processar_texto(
                mensagem.payload.decode(
                    "utf-8",
                    errors="replace",
                )
            )

        elif mensagem.topic == mqtt_client.TOPICO_FRAMES:
            _processar_frame(mensagem)

        elif mensagem.topic == mqtt_client.TOPICO_ARQUIVOS:
            _processar_arquivo_mqtt(mensagem)

        elif mensagem.topic.startswith(mqtt_client.TOPICO_PRESENCA_PREFIXO):
            _processar_presenca(mensagem)

    except Exception as erro:
        print(
            f"[rede_jarvis] Erro processando mensagem MQTT: {erro}"
        )


# Valida o token compartilhado e o destino de um envelope JSON.
# Mensagens sem o token correto, malformadas, ou destinadas a outra
# máquina são descartadas silenciosamente — não confirmamos a um
# atacante que o canal existe.
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

    # comandos.executar_comando pode envolver I/O bloqueante
    # (subprocess, busca em disco, etc.) e o fluxo de permissão espera
    # de forma síncrona — roda numa thread separada pra não travar a
    # thread de rede do paho-mqtt.
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

    if not mqtt_client.publicar_comando_json(envelope_resposta):
        print("[rede_jarvis] Falha ao enviar resposta pelo MQTT.")


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


def _processar_frame(mensagem):
    propriedades = mqtt_client.propriedades_para_dict(mensagem)

    if propriedades.get("token") != config.TOKEN_REDE_JARVIS:
        return

    if propriedades.get("destino") not in (config.NOME_MAQUINA, "todos"):
        return

    if _callback_frame_remoto:
        _callback_frame_remoto(
            mensagem.payload,
            propriedades.get("origem", "desconhecido"),
        )


def _processar_arquivo_mqtt(mensagem):
    propriedades = mqtt_client.propriedades_para_dict(mensagem)

    if propriedades.get("token") != config.TOKEN_REDE_JARVIS:
        return

    if propriedades.get("destino") not in (config.NOME_MAQUINA, "todos"):
        return

    from . import transferencia_arquivos

    transferencia_arquivos.receber_arquivo(
        propriedades.get("origem", "desconhecido"),
        propriedades.get("nome_arquivo", "arquivo_recebido"),
        mensagem.payload,
    )


def _processar_presenca(mensagem):
    try:
        dados = json.loads(
            mensagem.payload.decode(
                "utf-8",
                errors="replace",
            )
        )

    except (json.JSONDecodeError, TypeError):
        return

    if not isinstance(dados, dict):
        return

    if dados.get("token") != config.TOKEN_REDE_JARVIS:
        return

    maquina = dados.get("maquina")

    if not maquina:
        return

    with _LOCK_MAQUINAS:
        if dados.get("status") == "online":
            _MAQUINAS_ONLINE[maquina] = time.time()

        else:
            _MAQUINAS_ONLINE.pop(maquina, None)


# Lista as máquinas conhecidas como online agora — puramente local,
# a partir das mensagens de presença retidas já recebidas ao se
# inscrever no tópico (ver _ao_conectar). Não faz nenhuma chamada de
# rede na hora de responder.
def listar_maquinas_online():
    with _LOCK_MAQUINAS:
        maquinas = sorted(_MAQUINAS_ONLINE.keys())

    if not maquinas:
        return "Nenhuma máquina está online no momento."

    return "Máquinas online agora: " + ", ".join(maquinas)


# Envia um envelope e aguarda a resposta correlacionada por
# id_pedido (usado tanto para comandos remotos quanto para a consulta
# de client_email do Google Drive).
def _enviar_e_aguardar(envelope, timeout):
    id_pedido = envelope["id_pedido"]
    evento = threading.Event()
    container = {}

    with _LOCK_RESPOSTAS:
        _RESPOSTAS_PENDENTES[id_pedido] = (evento, container)

    enviado = mqtt_client.publicar_comando_json(
        json.dumps(envelope)
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
