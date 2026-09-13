import io
import wave

LARGURA_16_BITS = 2


def pcm_para_wav(
    pcm_bytes,
    taxa,
    canais=1,
):
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(canais)
        arquivo.setsampwidth(LARGURA_16_BITS)
        arquivo.setframerate(taxa)
        arquivo.writeframes(pcm_bytes)

    return buffer.getvalue()


def wav_para_pcm(dados_wav):
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
    bytes_por_quadro = LARGURA_16_BITS * canais

    if not taxa or not bytes_por_quadro:
        return 0.0

    return len(pcm_bytes) / (bytes_por_quadro * taxa)
