import json
import sys
import tempfile
import time

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.cerebro.voz_local import audio_wav
from jarvis.cerebro.voz_local import config as config_local
from jarvis.cerebro.voz_local.mqtt_voz import ClienteVozLocal

FRASE_PADRAO = "Olá, isto é um teste do servidor de voz local. Você está me ouvindo?"


def gerar_fala_wav(frase):
    import win32com.client

    caminho = Path(tempfile.gettempdir()) / "jarvis_teste_fala.wav"

    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(str(caminho), 3)

    voz = win32com.client.Dispatch("SAPI.SpVoice")
    voz.AudioOutputStream = stream
    voz.Speak(frase)

    stream.Close()

    return caminho.read_bytes()


class Coletor:
    def __init__(self):
        self.texto = None
        self.audio = None
        self.texto_resposta = None
        self.erro = None

    def ao_texto(self, payload):
        try:
            self.texto = json.loads(payload.decode("utf-8", errors="replace"))

        except ValueError as erro:
            self.erro = f"JSON ilegível em {config_local.TOPICO_TEXTO_SAIDA}: {erro}"

    def ao_audio(self, dados, texto=None):
        self.audio = dados
        self.texto_resposta = texto

    def ao_erro(self, texto):
        self.erro = texto

    def esperar(self, atributo, limite_segundos):
        limite = time.time() + limite_segundos

        while time.time() < limite:
            if getattr(self, atributo) is not None or self.erro is not None:
                return

            time.sleep(0.2)


def main():
    frase = sys.argv[1] if len(sys.argv) > 1 else FRASE_PADRAO

    print(f'Gerando fala: "{frase}"')

    try:
        wav = gerar_fala_wav(frase)

    except Exception as erro:
        print(f"Não foi possível gerar a fala com o SAPI: {erro}")

        return 1

    pcm, taxa, canais = audio_wav.wav_para_pcm(wav)

    print(
        f"  WAV gerado: {len(wav)} bytes, {taxa} Hz, {canais} canal(is), "
        f"{audio_wav.duracao_segundos(pcm, taxa, canais):.2f}s"
    )

    coletor = Coletor()

    cliente = ClienteVozLocal(
        ao_receber_texto=coletor.ao_texto,
        ao_receber_saida=coletor.ao_audio,
        ao_receber_erro=coletor.ao_erro,
    )

    sucesso, mensagem = cliente.conectar()

    print(
        f"Conexão em {config_local.VOZ_LOCAL_MQTT_HOST}:"
        f"{config_local.VOZ_LOCAL_MQTT_PORT} -> {mensagem}"
    )

    if not sucesso:
        return 1

    try:
        print(f"\nETAPA 1: publicando o áudio em {config_local.TOPICO_ENTRADA}")

        inicio = time.time()

        ok, msg = cliente.publicar_entrada(wav)
        print(f"  {msg}")

        if not ok:
            return 1

        print(
            f"  aguardando {config_local.TOPICO_TEXTO_SAIDA} "
            f"(até {config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS}s)..."
        )

        coletor.esperar("texto", config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS)

        if coletor.erro:
            print(f"\nRESULTADO: o servidor reportou erro: {coletor.erro}")
            print("  (o worker mostraria isso na interface e voltaria a escutar)")

            return 0

        if coletor.texto is None:
            print(
                f"\nRESULTADO: nenhuma transcrição em "
                f"{time.time() - inicio:.1f}s. "
                "É exatamente o caminho de timeout da etapa 1 do worker."
            )

            return 1

        texto = (coletor.texto.get("texto") or "").strip()

        print(f"  transcrição em {time.time() - inicio:.1f}s:")
        print(f"    texto = {texto!r}")
        print(f"    tom   = {coletor.texto.get('tom')!r}")
        print(f"    sexo  = {coletor.texto.get('sexo')!r}")

        if not texto:
            print("\nRESULTADO: transcrição vazia — o worker não seguiria daqui.")

            return 1

        print("\nROTEAMENTO: ferramenta ou conversa?")

        from jarvis import roteamento_hierarquico

        try:
            decisao = roteamento_hierarquico.processar_turno(texto, [])

        except Exception as erro:
            print(f"  roteamento falhou ({erro}); seguindo como conversa")
            decisao = None

        if decisao is not None and (
            decisao.usou_ferramenta or decisao.pedido_esclarecimento
        ):
            print(
                f"  -> FERRAMENTA ({decisao.ferramenta_executada}). "
                "A etapa 2 NÃO é chamada neste turno."
            )
            print(f"  resposta local: {decisao.resposta}")

            print(
                "\nRESULTADO: turno resolvido localmente, sem áudio — "
                "exatamente o comportamento especificado."
            )

            return 0

        print("  -> CONVERSA. Seguindo para a etapa 2.")

        print(
            f"\nETAPA 2: republicando o JSON em "
            f"{config_local.TOPICO_TEXTO_ENTRADA}"
        )

        inicio = time.time()

        ok, msg = cliente.publicar_texto(coletor.texto)
        print(f"  {msg}")

        if not ok:
            return 1

        print(
            f"  aguardando {config_local.TOPICO_SAIDA} "
            f"(até {config_local.TIMEOUT_RESPOSTA_SEGUNDOS}s)..."
        )

        coletor.erro = None
        coletor.esperar("audio", config_local.TIMEOUT_RESPOSTA_SEGUNDOS)

        if coletor.erro:
            print(f"\nRESULTADO: o servidor reportou erro: {coletor.erro}")

            return 0

        if coletor.audio is None:
            print(
                f"\nRESULTADO: nenhum áudio em {time.time() - inicio:.1f}s. "
                "É o caminho de timeout da etapa 2 do worker."
            )

            return 1

        print(
            f"\nRESULTADO: áudio recebido em {time.time() - inicio:.1f}s "
            f"({len(coletor.audio)} bytes)."
        )

        if coletor.texto_resposta:
            print(f"  texto da resposta: {coletor.texto_resposta!r}")

        else:
            print(
                "  ATENÇÃO: o servidor não mandou a user property "
                f"'{config_local.PROPRIEDADE_TEXTO_RESPOSTA}' — o "
                "histórico ficaria só com as falas do usuário."
            )

        try:
            pcm_resposta, taxa_resposta, canais_resposta = (
                audio_wav.wav_para_pcm(coletor.audio)
            )

        except ValueError as erro:
            print(f"  Mas não é um WAV que o playback aceita: {erro}")

            return 1

        duracao = audio_wav.duracao_segundos(
            pcm_resposta,
            taxa_resposta,
            canais_resposta,
        )

        print(
            f"  WAV válido: {taxa_resposta} Hz, {canais_resposta} canal(is), "
            f"{duracao:.2f}s de fala."
        )
        print("  O worker abriria o dispositivo de saída nessa taxa e tocaria.")

        return 0

    finally:
        cliente.desconectar()


if __name__ == "__main__":
    sys.exit(main())
