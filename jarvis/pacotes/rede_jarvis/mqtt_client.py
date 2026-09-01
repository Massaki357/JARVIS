# paho-mqtt fala o protocolo MQTT com o broker (ex: HiveMQ Cloud).
# Usamos MQTT5 (não MQTT 3.1.1) porque suas "user properties" deixam
# carregar metadados (token, origem, destino, nome do arquivo...)
# junto de um payload binário puro — sem precisar embrulhar frames e
# arquivos em JSON/base64, o que desperdiçaria parte do limite de
# tamanho da mensagem.
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes

from . import config

import json
import uuid

# Tópicos usados por todas as máquinas. O roteamento entre máquinas
# não é feito pelo tópico (que é o mesmo pra todo mundo), e sim pelos
# campos "token"/"destino" dentro de cada mensagem — assim como estava
# desenhado desde a primeira versão (com Telegram), só trocando o
# transporte por baixo.
TOPICO_COMANDOS = "jarvis/comandos"
TOPICO_FRAMES = "jarvis/frames"
TOPICO_ARQUIVOS = "jarvis/arquivos"

# Tópico de presença é um por máquina (não compartilhado como os
# outros), pra cada uma poder reter só a própria última mensagem sem
# sobrescrever a das outras.
TOPICO_PRESENCA_PREFIXO = "jarvis/presenca/"


def topico_presenca(nome_maquina):
    return f"{TOPICO_PRESENCA_PREFIXO}{nome_maquina}"

# Uma única instância do cliente por processo. Quem conecta e inicia
# o loop de rede é o mqtt_listener.py; publish() é thread-safe e pode
# ser chamado de qualquer lugar do pacote depois disso.
_cliente = None


def obter_cliente():
    global _cliente

    if _cliente is None:
        _cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"jarvis-{config.NOME_MAQUINA}-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv5,
        )

        if config.MQTT_USERNAME:
            _cliente.username_pw_set(
                config.MQTT_USERNAME,
                config.MQTT_PASSWORD,
            )

        # HiveMQ Cloud (e a maioria dos brokers na nuvem) exige TLS.
        # Sem argumentos, usa o conjunto padrão de certificados
        # confiáveis do sistema.
        _cliente.tls_set()

        # Testamento (Last Will): se a conexão cair de forma abrupta
        # (queda de rede, processo encerrado sem desconectar direito),
        # o PRÓPRIO BROKER publica esta mensagem em nome desta
        # máquina, marcando-a como offline — sem precisar de nenhum
        # heartbeat/ping ativo entre as máquinas. Precisa ser
        # configurado antes de connect().
        _cliente.will_set(
            topico_presenca(config.NOME_MAQUINA),
            json.dumps(
                {
                    "token": config.TOKEN_REDE_JARVIS,
                    "maquina": config.NOME_MAQUINA,
                    "status": "offline",
                }
            ),
            qos=1,
            retain=True,
        )

    return _cliente


def _propriedades(pares):
    propriedades = Properties(PacketTypes.PUBLISH)
    propriedades.UserProperty = [
        (chave, str(valor))
        for chave, valor in pares.items()
        if valor is not None
    ]

    return propriedades


def propriedades_para_dict(mensagem):
    pares = {}

    if mensagem.properties and hasattr(mensagem.properties, "UserProperty"):
        for chave, valor in mensagem.properties.UserProperty:
            pares[chave] = valor

    return pares


# Publica o status de presença desta máquina, retido no broker (o
# broker guarda e entrega a última mensagem retida pra todo mundo que
# se inscrever depois — não precisa esperar essa máquina publicar de
# novo pra saber o status atual dela).
def publicar_presenca(status):
    try:
        payload = json.dumps(
            {
                "token": config.TOKEN_REDE_JARVIS,
                "maquina": config.NOME_MAQUINA,
                "status": status,
            }
        )

        obter_cliente().publish(
            topico_presenca(config.NOME_MAQUINA),
            payload,
            qos=1,
            retain=True,
        )

        return True

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao publicar presença no MQTT: {erro}"
        )

        return False


# Publica um envelope JSON de comando/resposta (usado pelos tipos
# "comando", "resposta", "consulta_service_account", "arquivo_drive").
def publicar_comando_json(texto):
    try:
        info = obter_cliente().publish(
            TOPICO_COMANDOS,
            texto,
            qos=1,
        )

        info.wait_for_publish(timeout=15)

        return info.is_published()

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao publicar comando no MQTT: {erro}"
        )

        return False


# Publica um frame de imagem (usado por capturar_tela e pela
# visualização contínua remota). QoS 0: é um fluxo em tempo real,
# perder um frame ocasional não é grave, e o overhead menor ajuda a
# manter o intervalo entre frames.
def publicar_frame(frame_bytes, origem, destino, id_sessao):
    try:
        propriedades = _propriedades(
            {
                "token": config.TOKEN_REDE_JARVIS,
                "origem": origem,
                "destino": destino,
                "id_sessao": id_sessao,
            }
        )

        obter_cliente().publish(
            TOPICO_FRAMES,
            frame_bytes,
            qos=0,
            properties=propriedades,
        )

        return True

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao publicar frame no MQTT: {erro}"
        )

        return False


# Publica um arquivo (usado por enviar_arquivo, dentro do limite
# direto, e por capturar_tela, cujo resultado é tratado como um
# arquivo recebido do outro lado).
def publicar_arquivo(conteudo_bytes, origem, destino, nome_arquivo):
    try:
        propriedades = _propriedades(
            {
                "token": config.TOKEN_REDE_JARVIS,
                "origem": origem,
                "destino": destino,
                "nome_arquivo": nome_arquivo,
            }
        )

        info = obter_cliente().publish(
            TOPICO_ARQUIVOS,
            conteudo_bytes,
            qos=1,
            properties=propriedades,
        )

        info.wait_for_publish(timeout=30)

        return info.is_published()

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao publicar arquivo no MQTT: {erro}"
        )

        return False
