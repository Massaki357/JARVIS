# Cliente MQTT do cérebro de voz local — conexão PRÓPRIA com o broker
# do alfred-server (mosquitto em localhost:1884, sem TLS e sem
# autenticação; ver config.VOZ_LOCAL_MQTT_PORT para por que 1884 e
# não 1883).
#
# POR QUE NÃO REAPROVEITAR jarvis/pacotes/rede_jarvis/mqtt_client.py:
# aquele módulo mantém um único cliente por processo
# (obter_cliente()), apontado para o broker na nuvem do rede_jarvis, e
# chama tls_set() incondicionalmente além de configurar usuário/senha
# e um Last Will de presença. Um objeto do paho-mqtt é uma conexão
# para UM endereço — apontar a mesma instância também para o broker
# local é impossível, e generalizá-la mexeria num código já
# testado que carrega credenciais, sem ganho nenhum. Então este
# arquivo repete o FORMATO de lá (paho v2, MQTT5, callbacks nomeadas
# em português, nunca levantar exceção para fora) com uma conexão
# separada, e o rede_jarvis continua exatamente como estava.
#
# Diferente do de lá, aqui NÃO existe singleton: cada chamada de voz
# cria a sua instância e a desconecta ao terminar, do mesmo jeito que
# o worker é recriado a cada chamada.
import paho.mqtt.client as mqtt

from . import config

import json
import threading
import uuid


class ClienteVozLocal:
    """
    Conexão com o broker do servidor local.

    Os três callbacks — ao_receber_texto(json_bytes) para a ETAPA 1,
    ao_receber_saida(audio_bytes, texto_ou_None) para a ETAPA 2 e
    ao_receber_erro(texto) para as duas — são chamados a partir da
    THREAD DE REDE do paho, nunca do loop do worker; quem passa os
    callbacks é responsável por atravessar para o loop (o
    cliente_local.py faz isso com loop.call_soon_threadsafe).
    """

    def __init__(
        self,
        ao_receber_texto,
        ao_receber_saida,
        ao_receber_erro,
    ):
        self._ao_receber_texto = ao_receber_texto
        self._ao_receber_saida = ao_receber_saida
        self._ao_receber_erro = ao_receber_erro

        # Sinalizado pelo on_connect. conectar() espera nele em vez de
        # assumir que connect() já deixou a sessão pronta: o CONNACK
        # chega depois, na thread de rede.
        self._conectado = threading.Event()

        # Guarda o motivo de uma recusa do broker (usuário/senha
        # errados, por exemplo) para conectar() poder explicar a falha
        # em vez de só dizer "tempo esgotado".
        self._motivo_recusa = None

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

        # Desligado por padrão: um broker local não tem certificado.
        if config.VOZ_LOCAL_MQTT_TLS:
            self._cliente.tls_set()

        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_message = self._ao_receber_mensagem
        self._cliente.on_disconnect = self._ao_desconectar

    # ================================================================
    # CICLO DE VIDA
    # ================================================================

    def conectar(self):
        """
        Conecta e assina os tópicos de saída e de erro. Bloqueia até o
        broker confirmar (ou até TIMEOUT_CONEXAO_SEGUNDOS).

        Devolve (sucesso, mensagem) e nunca levanta exceção — mesma
        convenção de retorno usada pelos pacotes do projeto.
        """
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

        # loop_start() sobe a thread de rede interna do paho e retorna
        # na hora — a partir daqui os callbacks podem disparar.
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

    # ================================================================
    # PUBLICAÇÃO
    # ================================================================

    def publicar_entrada(self, audio_bytes):
        """
        ETAPA 1. Publica o arquivo de áudio INTEIRO em
        jarvis/audio/entrada — payload cru, sem JSON e sem base64, que
        é a convenção do servidor. Devolve (sucesso, mensagem).
        """
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
        """
        ETAPA 2. Republica em jarvis/texto/entrada o MESMO JSON que
        veio de jarvis/texto/saida — é o que o servidor espera, e é
        por isso que o dicionário é reenviado inteiro em vez de
        remontado campo a campo aqui.

        ensure_ascii=False: o texto é português e vai em UTF-8, como o
        servidor decodifica. Devolve (sucesso, mensagem).
        """
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

    # Publicação em si, comum às duas etapas: QoS 1 e confirmação do
    # broker antes de dar a operação por feita.
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

    # ================================================================
    # CALLBACKS DO PAHO (rodam na thread de rede dele)
    # ================================================================

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

        # As assinaturas ficam aqui, e não em conectar(), para serem
        # refeitas sozinhas se o paho reconectar depois de uma queda.
        # Uma lista só, e não três chamadas: as três são as respostas
        # do MESMO pipeline, e um reconnect que reassinasse só parte
        # delas deixaria o cliente meio surdo — o pior estado
        # possível, porque parece que funciona. (Mesmo raciocínio, e
        # mesma forma, do lado do servidor.)
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
        # Nunca deixa uma exceção subir para dentro da thread de rede
        # do paho: ela mataria o processamento das mensagens
        # seguintes em silêncio.
        try:
            if mensagem.topic == config.TOPICO_TEXTO_SAIDA:
                # ETAPA 1: JSON UTF-8 com texto/tom/sexo. Quem
                # interpreta é o worker — aqui só atravessa.
                self._ao_receber_texto(
                    mensagem.payload
                )

            elif mensagem.topic == config.TOPICO_SAIDA:
                # ETAPA 2: o WAV vem no payload e o TEXTO que o
                # servidor falou vem ao lado, como user property v5
                # (ver _texto_da_propriedade). O payload segue sendo
                # só os bytes do áudio, como sempre foi.
                self._ao_receber_saida(
                    mensagem.payload,
                    self._texto_da_propriedade(mensagem),
                )

            elif mensagem.topic == config.TOPICO_ERRO:
                # O servidor publica uma linha de texto UTF-8 dizendo
                # qual etapa do pipeline quebrou.
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
        """
        O texto da resposta, lido da user property "texto" da
        mensagem de áudio. Devolve None quando não vier.

        POR QUE ELE VEM COMO METADADO, e não dentro do payload: o
        payload de jarvis/audio/saida é o arquivo WAV inteiro, sem
        envelope — o mesmo contrato de jarvis/audio/entrada. Enfiar
        um JSON com o texto ali dentro obrigaria as duas pontas a
        empacotar e desempacotar o áudio, e quebraria qualquer
        cliente que hoje só grava o payload num arquivo. A property
        anda ao lado dos bytes, sem tocá-los. É o mesmo padrão de
        metadado-ao-lado-de-binário que jarvis/pacotes/rede_jarvis/
        já usa nos tópicos de frame e de arquivo.

        NUNCA LEVANTA. O texto é um bônus — serve para o histórico do
        turno seguinte —, e o áudio, que é o principal, já chegou.
        Perder o metadado custa um lado da conversa no histórico;
        deixar uma exceção subir daqui mataria a thread de rede do
        paho e, com ela, todas as mensagens seguintes.

        Um servidor antigo (ou uma conexão v3.1.1, onde properties
        simplesmente não existem no protocolo) devolve None aqui, e o
        turno segue igual ao que era antes deste campo existir.
        """
        try:
            propriedades = getattr(mensagem, "properties", None)

            # UserProperty é uma LISTA de pares (nome, valor), e não
            # um dict: o MQTT v5 permite o mesmo nome repetido. O
            # primeiro "texto" vence.
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
