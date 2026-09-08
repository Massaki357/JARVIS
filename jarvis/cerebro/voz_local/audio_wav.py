# Conversão entre o PCM cru que o sounddevice captura/toca e o
# arquivo WAV que o alfred-server troca pelos tópicos MQTT.
#
# Usa só a stdlib (módulo wave) — nenhuma dependência nova. O ffmpeg
# do servidor lê qualquer formato, mas WAV PCM 16 kHz mono é o caminho
# mais curto: é EXATAMENTE o que o microfone já entrega neste projeto
# (TAXA_ENTRADA=16000, CANAIS=1, int16), então gravar o arquivo é só
# colocar um cabeçalho na frente dos bytes, sem reamostrar nada.
import io
import wave

# Largura de amostra em bytes: 2 = 16 bits, o único formato que o
# sounddevice usa neste projeto (dtype="int16").
LARGURA_16_BITS = 2


def pcm_para_wav(
    pcm_bytes,
    taxa,
    canais=1,
):
    """
    Embrulha bytes PCM 16 bits num arquivo WAV completo, em memória.
    Devolve os bytes do arquivo — nada é escrito em disco (mesma
    regra das capturas de tela/câmera do projeto).
    """
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(canais)
        arquivo.setsampwidth(LARGURA_16_BITS)
        arquivo.setframerate(taxa)
        arquivo.writeframes(pcm_bytes)

    return buffer.getvalue()


def wav_para_pcm(dados_wav):
    """
    Lê um WAV vindo do servidor e devolve
    (pcm_bytes, taxa, canais).

    A taxa vem SEMPRE do cabeçalho do arquivo, nunca presumida: o
    servidor pode devolver 22050, 24000 ou qualquer outra coisa, e
    tocar num stream aberto na taxa errada deixa a voz acelerada ou
    arrastada. Quem chama abre o dispositivo de saída com a taxa que
    esta função devolveu.

    Levanta ValueError com uma mensagem legível quando o arquivo não
    é um WAV válido ou não está em 16 bits — o chamador transforma
    isso num erro visível na interface em vez de estourar no meio da
    reprodução.
    """
    if not dados_wav:
        raise ValueError(
            "O servidor local respondeu com um arquivo de áudio vazio."
        )

    try:
        with wave.open(io.BytesIO(dados_wav), "rb") as arquivo:
            largura = arquivo.getsampwidth()

            if largura != LARGURA_16_BITS:
                raise ValueError(
                    "O servidor local respondeu com um WAV de "
                    f"{largura * 8} bits; só 16 bits é suportado aqui."
                )

            canais = arquivo.getnchannels()
            taxa = arquivo.getframerate()
            pcm_bytes = arquivo.readframes(
                arquivo.getnframes()
            )

    except ValueError:
        # Já é a mensagem tratada acima — repassa sem reembrulhar.
        raise

    except wave.Error as erro:
        raise ValueError(
            f"O servidor local respondeu com um WAV inválido: {erro}"
        )

    except Exception as erro:
        raise ValueError(
            f"Não foi possível ler o áudio devolvido pelo servidor local: {erro}"
        )

    if not pcm_bytes:
        raise ValueError(
            "O servidor local respondeu com um WAV sem nenhuma amostra de áudio."
        )

    return pcm_bytes, taxa, canais


def duracao_segundos(
    pcm_bytes,
    taxa,
    canais=1,
):
    """
    Duração aproximada de um bloco de PCM 16 bits, em segundos. Usada
    pelo VAD para saber quando a frase atingiu a duração mínima/máxima
    sem precisar cronometrar relógio de parede (o que contaria também
    o tempo gasto processando).
    """
    bytes_por_quadro = LARGURA_16_BITS * canais

    if not taxa or not bytes_por_quadro:
        return 0.0

    return len(pcm_bytes) / (bytes_por_quadro * taxa)
