import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes

from . import config

import json
import uuid

TOPICO_COMANDOS = "jarvis/comandos"
TOPICO_FRAMES = "jarvis/frames"
TOPICO_ARQUIVOS = "jarvis/arquivos"

TOPICO_PRESENCA_PREFIXO = "jarvis/presenca/"


def topico_presenca(nome_maquina):
    return f"{TOPICO_PRESENCA_PREFIXO}{nome_maquina}"

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

        _cliente.tls_set()

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
