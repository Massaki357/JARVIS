import asyncio
import re
import sys
import unicodedata
from array import array

from google import genai
from google.genai import types

from jarvis.caminhos import garantir_pasta
from jarvis.nucleo.config import GEMINI_API_KEY, GEMINI_LIVE_MODEL, GEMINI_VOICE
from jarvis.servicos.aviso_ferramenta import (
    FERRAMENTAS_SEM_AVISO,
    NOME_GENERICO,
    TAXA_AMOSTRAGEM,
    frase_do_aviso,
    pasta_audios,
    wav_de_pcm,
)

FRASES_POR_SESSAO = 15

TENTATIVAS_POR_FRASE = 3

TIMEOUT_FRASE_SEGUNDOS = 40

LIMIAR_SILENCIO = 350

MARGEM_SEGUNDOS = 0.08

INSTRUCAO = (
    "Você é um leitor de frases, não um assistente. A cada mensagem, leia em "
    "voz alta, em português do Brasil, exatamente o texto recebido, palavra "
    "por palavra, sem acrescentar, cumprimentar, comentar ou responder nada."
)


def nomes_para_gerar():
    from jarvis.nucleo.perfis import catalogo_ferramentas

    nomes = set(catalogo_ferramentas.nomes_disponiveis()) | set(
        catalogo_ferramentas.NOMES_NATIVAS_OPENAI
    )

    return sorted(nomes - FERRAMENTAS_SEM_AVISO) + [NOME_GENERICO]


def _comparavel(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")

    return " ".join(re.sub(r"[^a-z0-9 ]", " ", texto).split())


def _aparar_silencio(pcm):
    amostras = array("h", pcm)

    inicio = 0
    fim = len(amostras)

    while inicio < fim and abs(amostras[inicio]) < LIMIAR_SILENCIO:
        inicio += 1

    while fim > inicio and abs(amostras[fim - 1]) < LIMIAR_SILENCIO:
        fim -= 1

    margem = int(TAXA_AMOSTRAGEM * MARGEM_SEGUNDOS)

    return amostras[max(0, inicio - margem):min(len(amostras), fim + margem)].tobytes()


async def _ler_frase(sessao, frase):
    await sessao.send_client_content(
        turns=[types.Content(role="user", parts=[types.Part(text=frase)])],
        turn_complete=True,
    )

    audio = bytearray()
    falado = []

    async for resposta in sessao.receive():
        if resposta.data:
            audio.extend(resposta.data)

        conteudo = resposta.server_content

        if conteudo and conteudo.output_transcription and conteudo.output_transcription.text:
            falado.append(conteudo.output_transcription.text)

        if conteudo and conteudo.turn_complete:
            break

    return bytes(audio), "".join(falado).strip()


async def _gerar_lote(cliente, nomes, pasta):
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
            )
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(parts=[types.Part(text=INSTRUCAO)]),
    )

    falhas = []

    async with cliente.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as sessao:
        for nome in nomes:
            frase = frase_do_aviso(nome)
            ultimo = ""

            for _ in range(TENTATIVAS_POR_FRASE):
                pcm, ultimo = await asyncio.wait_for(
                    _ler_frase(sessao, frase),
                    timeout=TIMEOUT_FRASE_SEGUNDOS,
                )

                # A transcrição é a prova de que o áudio diz só a frase, sem comentário do modelo.
                if pcm and _comparavel(ultimo) == _comparavel(frase):
                    pcm = _aparar_silencio(pcm)
                    (pasta / f"{nome}.wav").write_bytes(wav_de_pcm(pcm))

                    print(f"  ok    {nome}: {len(pcm) / 2 / TAXA_AMOSTRAGEM:.1f}s")
                    break

            else:
                falhas.append(nome)
                print(f"  FALHA {nome}: o áudio saiu diferente da frase ({ultimo!r})")

    return falhas


async def gerar(nomes=None, forcar=False):
    pasta = garantir_pasta(pasta_audios())

    pendentes = [
        nome
        for nome in (nomes or nomes_para_gerar())
        if forcar or not (pasta / f"{nome}.wav").is_file()
    ]

    print(
        f"[AVISO-FERRAMENTA] Gerando {len(pendentes)} áudio(s) com "
        f"{GEMINI_LIVE_MODEL}, voz {GEMINI_VOICE}, em {pasta}"
    )

    cliente = genai.Client(api_key=GEMINI_API_KEY)
    falhas = []

    for inicio in range(0, len(pendentes), FRASES_POR_SESSAO):
        lote = pendentes[inicio:inicio + FRASES_POR_SESSAO]

        try:
            falhas += await _gerar_lote(cliente, lote, pasta)

        except Exception as erro:
            print(f"  FALHA no lote {lote[0]}..{lote[-1]}: {type(erro).__name__}: {erro}")
            falhas += [nome for nome in lote if not (pasta / f"{nome}.wav").is_file()]

    return falhas


if __name__ == "__main__":
    restantes = asyncio.run(
        gerar(
            nomes=[n for n in sys.argv[1:] if not n.startswith("--")] or None,
            forcar="--forcar" in sys.argv,
        )
    )

    sys.exit(1 if restantes else 0)
