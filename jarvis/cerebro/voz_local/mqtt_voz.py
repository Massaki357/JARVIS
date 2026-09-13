import paho.mqtt.client as mqtt

from . import config

import json
import threading
import uuid


class ClienteVozLocal:
    def __init__(
        self,
        ao_receber_texto,
        ao_receber_saida,
        ao_receber_erro,
    ):
        self._ao_receber_texto = ao_receber_texto
        self._ao_receber_saida = ao_receber_saida
        self._ao_receber_erro = ao_receber_erro

        self._conectado = threading.Event()

        self._motivo_recusa = None

        # Cliente paho próprio: nunca rotear pelo broker da rede_jarvis (docs/voz_local.md).
        self._cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"jarvis-voz-local-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv5,
        )

        if config.VOZ_LOCAL_MQTT_USERNAME:
            self._cliente.username_pw_set(
                config.VOZ_LOCAL_MQTT_USERNAME,
                config.VOZ_LOCAL_MQTT_PASSWORD,
            )

        if config.VOZ_LOCAL_MQTT_TLS:
            self._cliente.tls_set()

        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_message = self._ao_receber_mensagem
        self._cliente.on_disconnect = self._ao_desconectar

    def conectar(self):
        try:
            self._cliente.connect(
                config.VOZ_LOCAL_MQTT_HOST,
                config.VOZ_LOCAL_MQTT_PORT,
                keepalive=60,
            )

        except Exception as erro:
            return (
                False,
                "Não foi possível conectar ao broker MQTT local em "
                f"{config.VOZ_LOCAL_MQTT_HOST}:{config.VOZ_LOCAL_MQTT_PORT} "
                f"({erro}). O alfred-server está rodando?",
            )

        self._cliente.loop_start()

        if not self._conectado.wait(
            timeout=config.TIMEOUT_CONEXAO_SEGUNDOS
        ):
            self.desconectar()

            if self._motivo_recusa is not None:
                return (
                    False,
                    "O broker MQTT local recusou a conexão "
                    f"({self._motivo_recusa}).",
                )

            return (
                False,
                "O broker MQTT local não respondeu em "
                f"{config.TIMEOUT_CONEXAO_SEGUNDOS}s.",
            )

        return (
            True,
            "Conectado ao servidor de voz local.",
        )

    def desconectar(self):
        try:
            self._cliente.loop_stop()
            self._cliente.disconnect()

        except Exception as erro:
            print(
                f"[VOZ LOCAL] Falha ao desconectar do broker: {erro}"
            )

    def publicar_entrada(self, audio_bytes):
        tamanho_mb = len(audio_bytes) / (1024 * 1024)

        if tamanho_mb > config.LIMITE_ENVIO_MB:
            return (
                False,
                f"O áudio capturado ficou grande demais ({tamanho_mb:.1f} MB) "
                f"para o limite de {config.LIMITE_ENVIO_MB} MB.",
            )

        return self._publicar(
            config.TOPICO_ENTRADA,
            audio_bytes,
            "o áudio",
        )

    def publicar_texto(self, dados):
        try:
            payload = json.dumps(
                dados,
                ensure_ascii=False,
            ).encode("utf-8")

        except (TypeError, ValueError) as erro:
            return (
                False,
                f"Não foi possível montar o JSON da transcrição: {erro}",
            )

        return self._publicar(
            config.TOPICO_TEXTO_ENTRADA,
            payload,
            "o texto",
        )

    def _publicar(self, topico, payload, descricao):
        try:
            info = self._cliente.publish(
                topico,
                payload,
                qos=1,
            )

            info.wait_for_publish(timeout=15)

            if not info.is_published():
                return (
                    False,
                    f"O broker MQTT local não confirmou o envio d{descricao} "
                    f"em {topico}.",
                )

            return (
                True,
                f"Enviei {descricao} para {topico}.",
            )

        except Exception as erro:
            return (
                False,
                f"Falha ao publicar {descricao} em {topico}: {erro}",
            )

    def _ao_conectar(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code != 0:
            self._motivo_recusa = reason_code

            print(
                f"[VOZ LOCAL] Broker recusou a conexão: {reason_code}"
            )

            return

        client.subscribe(
            [
                (config.TOPICO_TEXTO_SAIDA, 1),
                (config.TOPICO_SAIDA, 1),
                (config.TOPICO_ERRO, 1),
            ]
        )

        print("[VOZ LOCAL] Conectado ao broker MQTT local.")

        self._conectado.set()

    def _ao_desconectar(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        print(
            f"[VOZ LOCAL] Desconectado do broker local ({reason_code}). "
            "O paho-mqtt tenta reconectar sozinho."
        )

    def _ao_receber_mensagem(
        self,
        client,
        userdata,
        mensagem,
    ):
        try:
            if mensagem.topic == config.TOPICO_TEXTO_SAIDA:
                self._ao_receber_texto(
                    mensagem.payload
                )

            elif mensagem.topic == config.TOPICO_SAIDA:
                self._ao_receber_saida(
                    mensagem.payload,
                    self._texto_da_propriedade(mensagem),
                )

            elif mensagem.topic == config.TOPICO_ERRO:
                self._ao_receber_erro(
                    mensagem.payload.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()
                )

        except Exception as erro:
            print(
                f"[VOZ LOCAL] Falha ao processar mensagem de "
                f"{mensagem.topic}: {erro}"
            )

    @staticmethod
    def _texto_da_propriedade(mensagem):
        try:
            propriedades = getattr(mensagem, "properties", None)

            for nome, valor in (
                getattr(propriedades, "UserProperty", None) or []
            ):
                if nome == config.PROPRIEDADE_TEXTO_RESPOSTA:
                    texto = (valor or "").strip()

                    return texto or None

        except Exception as erro:
            print(
                f"[VOZ LOCAL] Não consegui ler o texto da resposta "
                f"nas propriedades da mensagem: {erro}"
            )

        return None
