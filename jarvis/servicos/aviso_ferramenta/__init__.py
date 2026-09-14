import io
import wave

from jarvis.caminhos import PASTA_DADOS
from jarvis.nucleo import modelos

LIMITE_SEGUNDOS = 1.5

TAXA_AMOSTRAGEM = 24000

NOME_GENERICO = "_generico"

FERRAMENTAS_SEM_AVISO = frozenset(
    {
        "executar_ferramenta",
        "pausar_chamada",
        "encerrar_chamada",
    }
)

_ACENTOS = {
    "acao": "ação",
    "admin": "administrador",
    "area": "área",
    "basico": "básico",
    "camera": "câmera",
    "configuracoes": "configurações",
    "continua": "contínua",
    "cotacao": "cotação",
    "dm": "DM",
    "historico": "histórico",
    "informacao": "informação",
    "instrucao": "instrução",
    "maquinas": "máquinas",
    "memoria": "memória",
    "memorias": "memórias",
    "opiniao": "opinião",
    "permissao": "permissão",
    "transferencia": "transferência",
    "visualizacao": "visualização",
    "youtube": "YouTube",
}

_cache_pcm = {}


def pasta_audios():
    return PASTA_DADOS / "audios" / "avisos_ferramenta" / modelos.modelo(
        "cerebro.gemini.voz"
    )


def nome_falado(nome_ferramenta):
    falado = " ".join(
        _ACENTOS.get(parte, parte)
        for parte in str(nome_ferramenta or "").split("_")
        if parte
    )

    return falado.replace("área trabalho", "área de trabalho")


def frase_do_aviso(nome_ferramenta):
    if nome_ferramenta == NOME_GENERICO:
        return "Só um minuto, estou executando uma ferramenta."

    return (
        "Só um minuto, estou executando a ferramenta "
        f"{nome_falado(nome_ferramenta)}."
    )


def ferramenta_do_aviso(chamadas, silenciosas=()):
    for nome, argumentos in chamadas:
        if nome == "executar_ferramenta":
            nome = str((argumentos or {}).get("nome") or "").strip()

        if not nome or nome in FERRAMENTAS_SEM_AVISO or nome in silenciosas:
            continue

        return nome

    return None


def _ler_pcm(caminho):
    with wave.open(str(caminho), "rb") as arquivo:
        if (
            arquivo.getframerate() != TAXA_AMOSTRAGEM
            or arquivo.getnchannels() != 1
            or arquivo.getsampwidth() != 2
        ):
            return None

        return arquivo.readframes(arquivo.getnframes())


def pcm_do_aviso(nome_ferramenta):
    pasta = pasta_audios()

    for candidato in (nome_ferramenta, NOME_GENERICO):
        caminho = pasta / f"{candidato}.wav"
        chave = str(caminho)

        if chave in _cache_pcm:
            return _cache_pcm[chave]

        if not caminho.is_file():
            continue

        try:
            pcm = _ler_pcm(caminho)

        except (OSError, wave.Error, EOFError) as erro:
            print(f"[AVISO-FERRAMENTA] Áudio ilegível em {caminho.name}: {erro}")
            continue

        if pcm:
            _cache_pcm[chave] = pcm
            return pcm

    return None


def wav_de_pcm(pcm):
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(TAXA_AMOSTRAGEM)
        arquivo.writeframes(pcm)

    return buffer.getvalue()
