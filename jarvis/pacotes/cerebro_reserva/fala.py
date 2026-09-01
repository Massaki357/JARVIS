# Falar: transforma o texto da resposta em voz.
#
# Três provedores, cada um verificado pelo mesmo teste objetivo —
# sintetizar uma frase em português e transcrevê-la de volta com o
# Whisper — já que não dá pra julgar áudio lendo código, só confirmar
# que a voz realmente pronuncia português (não só que a chamada
# respondeu 200):
#
#   edge-tts (voz neural Microsoft)  ~1,6s   grátis, sem conta, precisa de rede
#   SAPI local (voz Maria pt-BR)     0,10s   sem rede, sem cota
#   Mistral voxtral-mini-tts         2,0s    consome cota, precisa de rede
#
# Os três bateram 100% no teste de transcrição — mas ouvindo de
# verdade, o usuário achou a Mistral com sotaque ruim em português, e
# pediu uma voz melhor que o SAPI. edge-tts (config.PROVEDOR_VOZ_PREFERIDO,
# padrão "edge") é o resultado: voz neural, muito mais natural que o
# SAPI, e sem o custo/sotaque que tirou a Mistral da posição principal.
# SAPI continua em segundo por ser a opção mais resiliente (não
# depende de rede, e uma das causas do Gemini falhar é justamente a
# rede estar instável) — Mistral fica como último recurso.
import asyncio
import base64
import threading

import edge_tts
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

    # Acelera a fala (ver VELOCIDADE_VOZ_LOCAL) — pedido explícito do
    # usuário: a voz padrão do Windows soa lenta demais, e no modo
    # reserva uma resposta rápida importa mais que soar perfeita.
    voz.Rate = config.VELOCIDADE_VOZ_LOCAL

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


# Gera o áudio via edge-tts (assíncrono por natureza — biblioteca
# baseada em WebSocket) e reaproveita _reproduzir_mp3 pra tocar,
# exatamente como a Mistral já faz — os dois entregam MP3, só a forma
# de obter os bytes muda. asyncio.run() é seguro aqui porque falar()
# sempre roda numa thread comum (via asyncio.to_thread, do lado de
# cliente_live.py), nunca dentro de um loop assíncrono já em
# andamento — não há loop pra conflitar.
async def _sintetizar_edge(texto):
    comunicador = edge_tts.Communicate(texto, config.VOZ_EDGE)
    pedacos = []

    async for pedaco in comunicador.stream():
        if pedaco["type"] == "audio":
            pedacos.append(pedaco["data"])

    return b"".join(pedacos)


def _falar_edge(texto):
    try:
        audio_bytes = asyncio.run(_sintetizar_edge(texto))

    except Exception as erro:
        return False, f"Voz neural por rede indisponível: {erro}"

    if not audio_bytes:
        return False, "Voz neural por rede não retornou áudio."

    return _reproduzir_mp3(audio_bytes)


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


_PROVEDORES_VOZ = {
    "edge": _falar_edge,
    "local": _falar_local,
    "mistral": _falar_mistral,
}

# Ordem usada quando o preferido (config.PROVEDOR_VOZ_PREFERIDO) falha
# — os outros dois nesta ordem fixa, pulando o que já foi tentado.
_ORDEM_PADRAO_VOZ = ("edge", "local", "mistral")


# Fala o texto. Devolve (sucesso, mensagem_de_erro) e nunca levanta
# exceção. Tenta o provedor preferido primeiro (config.PROVEDOR_VOZ_PREFERIDO)
# e, se falhar, os outros dois na ordem fixa acima — ficar mudo é a
# pior falha possível para um assistente de voz.
def falar(texto):
    texto = (texto or "").strip()

    if not texto:
        return False, "Nada para falar."

    preferido = config.PROVEDOR_VOZ_PREFERIDO
    ordem = [preferido] + [
        nome for nome in _ORDEM_PADRAO_VOZ if nome != preferido
    ]

    erros = []

    for nome in ordem:
        sucesso, erro = _PROVEDORES_VOZ[nome](texto)

        if sucesso:
            return True, ""

        erros.append(erro)

    return False, " / ".join(erros)
