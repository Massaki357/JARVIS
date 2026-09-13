import difflib
import json
import re
import threading
import unicodedata

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from . import config


TAXA_AMOSTRAGEM_VOSK = 16000
TAMANHO_BLOCO_VOSK = 4000

CORTE_SIMILARIDADE = 0.72

_modelo = None

_stream = None
_thread = None
_parar_evento = threading.Event()

_callback_ativacao = None


def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def _palavra_esta_presente(palavra_alvo, palavras_texto):
    if palavra_alvo in palavras_texto:
        return True

    return bool(
        difflib.get_close_matches(
            palavra_alvo,
            palavras_texto,
            n=1,
            cutoff=CORTE_SIMILARIDADE,
        )
    )


def _contem_palavra_ativacao(texto_reconhecido):
    alvo = _normalizar(config.NOME_ATIVACAO)

    if not alvo:
        return False

    texto_normalizado = _normalizar(texto_reconhecido)

    if not texto_normalizado:
        return False

    if alvo in texto_normalizado:
        return True

    palavras_alvo = alvo.split(" ")
    palavras_texto = texto_normalizado.split(" ")

    if len(palavras_alvo) > 1:
        return all(
            _palavra_esta_presente(
                palavra_alvo,
                palavras_texto,
            )
            for palavra_alvo in palavras_alvo
        )

    return _palavra_esta_presente(
        alvo,
        palavras_texto,
    )


def _obter_modelo():
    global _modelo

    if _modelo is None:
        _modelo = Model(lang="pt")

    return _modelo


def _loop_deteccao():
    global _stream, _thread

    try:
        try:
            modelo = _obter_modelo()

        except Exception as erro:
            print(
                f"[ativacao_voz] Não foi possível carregar o modelo "
                f"de reconhecimento de voz: {erro}"
            )
            return

        if _parar_evento.is_set():
            return

        reconhecedor = KaldiRecognizer(
            modelo,
            TAXA_AMOSTRAGEM_VOSK,
        )

        try:
            _stream = sd.RawInputStream(
                samplerate=TAXA_AMOSTRAGEM_VOSK,
                blocksize=TAMANHO_BLOCO_VOSK,
                dtype="int16",
                channels=1,
            )

        except Exception as erro:
            print(
                f"[ativacao_voz] Não foi possível abrir o "
                f"microfone: {erro}"
            )
            return

        with _stream:
            while not _parar_evento.is_set():
                dados, _overflowed = _stream.read(
                    TAMANHO_BLOCO_VOSK
                )

                dados_bytes = bytes(dados)

                if reconhecedor.AcceptWaveform(dados_bytes):
                    texto = json.loads(
                        reconhecedor.Result()
                    ).get("text", "")
                else:
                    texto = json.loads(
                        reconhecedor.PartialResult()
                    ).get("partial", "")

                if texto and _contem_palavra_ativacao(texto):
                    if _callback_ativacao:
                        _callback_ativacao()

                    break

    finally:
        _stream = None
        _thread = None


def _abrir():
    global _thread

    if _thread is not None:
        return True

    _parar_evento.clear()

    _thread = threading.Thread(
        target=_loop_deteccao,
        daemon=True,
    )

    _thread.start()

    return True


def iniciar(callback_ativacao):
    global _callback_ativacao

    _callback_ativacao = callback_ativacao

    return _abrir()


def pausar():
    _parar_evento.set()

    thread_atual = _thread

    if thread_atual is not None:
        thread_atual.join(timeout=30)


def retomar():
    _abrir()


def esta_ativo():
    return _thread is not None
