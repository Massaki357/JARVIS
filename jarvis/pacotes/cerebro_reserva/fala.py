# Falar: transforma o texto da resposta em voz.
#
# Por padrão usa a voz do próprio Windows (SAPI), não uma API:
#
#   SAPI local (voz Maria pt-BR)  0,10s   sem rede, sem cota
#   Mistral voxtral-mini-tts      2,0s    consome cota, precisa de rede
#
# As duas foram verificadas pelo mesmo teste objetivo — sintetizar
# uma frase em português e transcrevê-la de volta com o Whisper — e
# as duas voltaram idênticas (100%). Como não dá para julgar áudio
# lendo código, essa ida e volta é a forma de confirmar que a voz
# realmente pronuncia português, e não só que a chamada respondeu 200.
#
# A local é o padrão por um motivo que importa aqui especificamente:
# este pacote existe para quando o Gemini falha, e uma das causas
# possíveis é a rede. Uma voz que depende de rede escolheria
# justamente a hora errada para falhar junto.
import base64
import threading

import requests

from . import config

# O objeto SAPI é criado uma vez e reaproveitado. COM em processo com
# Qt já inicializado é seguro aqui (mesma situação de
# SHGetKnownFolderPath em jarvis/servicos/visao/captura_tela.py), mas
# a criação é preguiçosa mesmo assim: nada de COM acontece se o modo
# reserva nunca for acionado.
_voz_sapi = None
_LOCK = threading.Lock()


def _obter_voz_sapi():
    global _voz_sapi

    if _voz_sapi is not None:
        return _voz_sapi

    import win32com.client

    voz = win32com.client.Dispatch("SAPI.SpVoice")

    # Procura uma voz cuja descrição contenha TRECHO_VOZ_LOCAL
    # ("Portuguese", por padrão). Se não houver nenhuma instalada,
    # segue com a voz padrão do sistema em vez de falhar — falar com
    # sotaque errado é melhor que emudecer.
    for token in voz.GetVoices():
        try:
            descricao = token.GetDescription()

        except Exception:
            continue

        if config.TRECHO_VOZ_LOCAL.lower() in descricao.lower():
            voz.Voice = token
            break

    _voz_sapi = voz

    return _voz_sapi


# Fala usando o Windows. Bloqueia até terminar de falar, de propósito:
# o laço do modo reserva não pode voltar a gravar o microfone
# enquanto a resposta ainda está tocando, senão o jarvis se ouviria.
def _falar_local(texto):
    try:
        with _LOCK:
            _obter_voz_sapi().Speak(texto)

        return True, ""

    except Exception as erro:
        return False, f"Voz local indisponível: {erro}"


def _falar_mistral(texto):
    if not config.MISTRAL_API_KEY:
        return False, "MISTRAL_API_KEY não configurada no .env."

    try:
        resposta = requests.post(
            config.URL_MISTRAL_FALA,
            headers={
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
            },
            json={
                "model": config.MODELO_FALA_MISTRAL,
                "input": texto,
                "voice": config.VOZ_MISTRAL,
            },
            timeout=config.TIMEOUT_FALA_SEGUNDOS,
        )

        if resposta.status_code != 200:
            return False, (
                f"Voz por rede falhou (HTTP {resposta.status_code})."
            )

        # A resposta é JSON com o MP3 em base64 no campo audio_data —
        # NÃO são bytes de áudio crus no corpo, como a API estilo
        # OpenAI faria. Confirmado ao vivo; tratar como bytes crus
        # gera um arquivo inválido silenciosamente.
        dados = resposta.json()
        audio_bytes = base64.b64decode(dados["audio_data"])

    except requests.Timeout:
        return False, "Tempo esgotado ao gerar a voz."

    except requests.RequestException as erro:
        return False, f"Falha ao gerar a voz: {erro}"

    except (KeyError, ValueError) as erro:
        return False, f"Resposta inesperada da voz: {erro}"

    return _reproduzir_mp3(audio_bytes)


# Toca o MP3 recebido. Usa o próprio SAPI (SpAudioFormat não lê MP3),
# então recorre ao reprodutor do Windows via COM — se falhar, o texto
# ainda foi produzido, e quem chamou decide o que fazer.
def _reproduzir_mp3(audio_bytes):
    import os
    import tempfile

    caminho = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
        ) as arquivo:
            arquivo.write(audio_bytes)
            caminho = arquivo.name

        import win32com.client

        reprodutor = win32com.client.Dispatch("WMPlayer.OCX")
        midia = reprodutor.newMedia(caminho)
        reprodutor.currentPlaylist.appendItem(midia)
        reprodutor.controls.play()

        # Espera a duração do áudio antes de liberar o microfone.
        import time

        limite = time.monotonic() + config.TIMEOUT_FALA_SEGUNDOS

        while time.monotonic() < limite:
            time.sleep(0.2)

            try:
                if reprodutor.playState == 1:  # 1 = parado/terminado
                    break

            except Exception:
                break

        return True, ""

    except Exception as erro:
        return False, f"Não foi possível reproduzir a voz: {erro}"

    finally:
        if caminho:
            try:
                os.unlink(caminho)

            except OSError:
                pass


# Fala o texto. Devolve (sucesso, mensagem_de_erro) e nunca levanta
# exceção. Se a voz preferida falhar, tenta a outra antes de desistir
# — ficar mudo é a pior falha possível para um assistente de voz.
def falar(texto):
    texto = (texto or "").strip()

    if not texto:
        return False, "Nada para falar."

    if config.USAR_VOZ_LOCAL:
        sucesso, erro = _falar_local(texto)

        if sucesso:
            return True, ""

        sucesso, erro_rede = _falar_mistral(texto)

        return sucesso, ("" if sucesso else f"{erro} / {erro_rede}")

    sucesso, erro = _falar_mistral(texto)

    if sucesso:
        return True, ""

    sucesso, erro_local = _falar_local(texto)

    return sucesso, ("" if sucesso else f"{erro} / {erro_local}")
