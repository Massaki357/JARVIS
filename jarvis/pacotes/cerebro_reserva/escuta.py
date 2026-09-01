# Ouvir: captura o microfone até o usuário parar de falar e devolve o
# texto transcrito.
#
# No modo reserva não existe mais o streaming contínuo do Gemini
# Live, então a captura vira "grave um trecho, transcreva, responda"
# — turno a turno. A detecção de fim de fala é por energia do sinal
# (RMS), sem depender de serviço nenhum: fala começa quando o volume
# passa de LIMIAR_VOZ e termina depois de SILENCIO_FIM_FALA_SEGUNDOS
# abaixo dele.
#
# A transcrição usa o Whisper da Groq. Escolha medida, não assumida:
# transcreveu português brasileiro com 100% de acerto em 0,70s, e o
# limite de tokens de chat da Groq (8.000/min, apertado demais para o
# cérebro) não se aplica aqui, porque o Whisper é um modelo separado
# com cota própria.
import array
import io
import math
import queue
import time
import wave

import requests
import sounddevice as sd

from . import config


# RMS de um bloco de áudio int16. Feito na mão com array em vez de
# audioop: audioop foi removido do Python 3.13 em diante, e depender
# dele deixaria este pacote quebrado na próxima atualização.
def _volume(bloco_bytes):
    amostras = array.array("h")
    amostras.frombytes(bloco_bytes)

    if not amostras:
        return 0.0

    soma = 0

    for amostra in amostras:
        soma += amostra * amostra

    return math.sqrt(soma / len(amostras))


# Empacota os blocos crus em um WAV na memória — nenhum arquivo é
# escrito em disco (ver a regra "evitar escrita em disco" no
# CLAUDE.md; aqui o áudio é só um payload de requisição). Pública
# (não mais _montar_wav) porque jarvis/gemini/cliente_live.py também
# monta um WAV a partir do buffer circular de microfone, pra primar a
# primeira escuta do reserva com o áudio que o usuário já falou — ver
# ouvir()/config.py e _conduzir_reserva_temporaria.
def montar_wav(blocos):
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(config.CANAIS_AUDIO)
        arquivo.setsampwidth(2)
        arquivo.setframerate(config.TAXA_AUDIO)
        arquivo.writeframes(b"".join(blocos))

    return buffer.getvalue()


# Lê um bloco de config.BLOCO_AUDIO amostras — de fila_bloco_externa
# (um queue.Queue comum já alimentado por fora, ver
# cliente_live.py:enviar_microfone) quando fornecida, ou direto do
# stream próprio (entrada) caso contrário. Mantém gravar_fala() com um
# único laço em vez de duplicar a lógica de VAD pras duas fontes.
def _ler_bloco(entrada, fila_bloco_externa, deve_continuar):
    if fila_bloco_externa is not None:
        while True:
            if not deve_continuar():
                return None

            try:
                return fila_bloco_externa.get(timeout=0.2)

            except queue.Empty:
                continue

    bloco, _ = entrada.read(config.BLOCO_AUDIO)
    return bytes(bloco)


# Grava um trecho de fala e devolve os bytes de um WAV, ou None se
# ninguém falou dentro de ESPERA_MAXIMA_SILENCIO_SEGUNDOS.
#
# deve_continuar() é consultado durante a espera para o modo reserva
# poder ser encerrado (usuário desligou a chamada) sem ficar preso
# aqui esperando alguém falar.
#
# fila_bloco_externa (queue.Queue comum, opcional): quando fornecida,
# os blocos de áudio vêm de lá em vez de um sd.RawInputStream próprio
# — usado quando este pacote assume a conversa NO MEIO de uma chamada
# do Gemini ainda ativa (jarvis/gemini/cliente_live.py), pra nunca
# abrir um segundo stream de microfone concorrente com o que o Gemini
# já mantém aberto (mesmo risco de interferência já medido e
# documentado pro device de câmera, ver jarvis/pacotes/camera_preview/
# no CLAUDE.md — aqui resolvido reaproveitando a captura existente em
# vez de replicar aquele mecanismo de handle compartilhado, que foi
# desenhado pra captura pontual, não streaming contínuo). Sem este
# parâmetro, o comportamento é 100% o de antes — o pacote continua
# funcionando de forma standalone, decoupled, como já é documentado.
def gravar_fala(deve_continuar, fila_bloco_externa=None):
    blocos = []
    falou = False
    inicio = time.monotonic()
    ultimo_som = None

    duracao_bloco = config.BLOCO_AUDIO / config.TAXA_AUDIO

    def _laco(entrada):
        nonlocal blocos, falou, ultimo_som

        while True:
            if not deve_continuar():
                return None

            bloco = _ler_bloco(entrada, fila_bloco_externa, deve_continuar)

            if bloco is None:
                return None

            agora = time.monotonic()
            tem_voz = _volume(bloco) >= config.LIMIAR_VOZ

            if tem_voz:
                if not falou:
                    falou = True

                ultimo_som = agora
                blocos.append(bloco)

            elif falou:
                # Continua gravando o silêncio curto entre palavras —
                # cortar aqui picotaria a frase no meio.
                blocos.append(bloco)

                if (
                    agora - ultimo_som
                    >= config.SILENCIO_FIM_FALA_SEGUNDOS
                ):
                    break

            else:
                # Ainda ninguém falou: nada é acumulado, para não
                # transcrever minutos de silêncio.
                if (
                    agora - inicio
                    >= config.ESPERA_MAXIMA_SILENCIO_SEGUNDOS
                ):
                    return None

            if falou and (
                len(blocos) * duracao_bloco
                >= config.DURACAO_MAXIMA_FALA_SEGUNDOS
            ):
                break

        return True

    if fila_bloco_externa is not None:
        resultado = _laco(None)
    else:
        with sd.RawInputStream(
            samplerate=config.TAXA_AUDIO,
            blocksize=config.BLOCO_AUDIO,
            dtype="int16",
            channels=config.CANAIS_AUDIO,
        ) as entrada:
            resultado = _laco(entrada)

    if resultado is None or not blocos:
        return None

    return montar_wav(blocos)


# Transcreve o WAV. Devolve (sucesso, texto_ou_erro) — nunca levanta
# exceção, mesma convenção de retorno usada por todos os pacotes
# deste projeto.
def transcrever(wav_bytes):
    if not config.GROQ_API_KEY:
        return False, "GROQ_API_KEY não configurada no .env."

    if not wav_bytes:
        return False, "Nenhum áudio para transcrever."

    try:
        resposta = requests.post(
            config.URL_GROQ_TRANSCRICAO,
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
            },
            files={
                "file": (
                    "fala.wav",
                    io.BytesIO(wav_bytes),
                    "audio/wav",
                ),
            },
            data={
                "model": config.MODELO_TRANSCRICAO,
                "language": "pt",
            },
            timeout=config.TIMEOUT_TRANSCRICAO_SEGUNDOS,
        )

        if resposta.status_code != 200:
            return False, (
                f"Transcrição falhou (HTTP {resposta.status_code})."
            )

        texto = (resposta.json().get("text") or "").strip()

        if not texto:
            return False, "Transcrição vazia."

        return True, texto

    except requests.Timeout:
        return False, "Tempo esgotado ao transcrever o áudio."

    except requests.RequestException as erro:
        return False, f"Falha ao transcrever: {erro}"

    except ValueError as erro:
        return False, f"Resposta inesperada da transcrição: {erro}"


# Grava e transcreve de uma vez. Devolve None quando não houve fala
# (silêncio ou chamada encerrada), ou (sucesso, texto_ou_erro).
# audio_wav_pronto (bytes WAV, opcional): quando fornecido, PULA a
# gravação inteiramente e transcreve esse áudio direto — usado só na
# primeira chamada de um "assumir()" acionado no meio de uma chamada
# do Gemini já ativa (ver jarvis/gemini/cliente_live.py:
# _conduzir_reserva_temporaria), pra aproveitar o áudio que o usuário
# JÁ tinha falado (capturado num buffer circular enquanto esperava o
# Gemini responder) em vez de esperar ele repetir a pergunta.
def ouvir(deve_continuar, fila_bloco_externa=None, audio_wav_pronto=None):
    if audio_wav_pronto is not None:
        return transcrever(audio_wav_pronto)

    wav_bytes = gravar_fala(deve_continuar, fila_bloco_externa=fila_bloco_externa)

    if wav_bytes is None:
        return None

    return transcrever(wav_bytes)
