# requests faz as chamadas HTTP para a API do Bot do Telegram.
# Este módulo não usa nenhuma biblioteca específica de bot (como
# python-telegram-bot) de propósito: são poucas chamadas simples,
# então usar a API HTTP crua diretamente evita mais uma dependência
# pesada e mantém o pacote fácil de copiar para outro projeto.
import requests

from . import config


def _url(metodo):
    return (
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"
    )


# Envia uma mensagem de texto simples (usada para os envelopes JSON
# de comando/resposta).
def enviar_mensagem(chat_id, texto):
    try:
        resposta = requests.post(
            _url("sendMessage"),
            data={
                "chat_id": chat_id,
                "text": texto[:4096],
            },
            timeout=15,
        )

        return resposta.ok

    except requests.RequestException as erro:
        print(
            f"[rede_jarvis] Falha ao enviar mensagem pelo Telegram: {erro}"
        )

        return False


# Envia uma foto (usada por capturar_tela e pela visualização
# contínua remota, frame a frame).
def enviar_foto(chat_id, imagem_bytes, legenda=""):
    try:
        resposta = requests.post(
            _url("sendPhoto"),
            data={
                "chat_id": chat_id,
                "caption": legenda[:1024],
            },
            files={
                "photo": (
                    "frame.jpg",
                    imagem_bytes,
                    "image/jpeg",
                )
            },
            timeout=30,
        )

        return resposta.ok

    except requests.RequestException as erro:
        print(
            f"[rede_jarvis] Falha ao enviar foto pelo Telegram: {erro}"
        )

        return False


# Envia um arquivo como documento (usado por enviar_arquivo quando o
# arquivo está dentro do limite do Telegram).
def enviar_documento(chat_id, caminho_arquivo, legenda=""):
    try:
        with open(caminho_arquivo, "rb") as arquivo:
            resposta = requests.post(
                _url("sendDocument"),
                data={
                    "chat_id": chat_id,
                    "caption": legenda[:1024],
                },
                files={
                    "document": arquivo
                },
                timeout=120,
            )

        return resposta.ok

    except (requests.RequestException, OSError) as erro:
        print(
            f"[rede_jarvis] Falha ao enviar documento pelo Telegram: {erro}"
        )

        return False


# Consulta novas mensagens recebidas pelo bot desde "offset".
#
# AVISO: como várias máquinas compartilham o mesmo token de bot, o
# Telegram só permite um consumidor de getUpdates de cada vez — chamadas
# concorrentes de máquinas diferentes podem retornar 409 (conflito).
# Por isso usamos aqui um timeout curto de long-polling (o listener
# chama esta função repetidamente, com uma pequena pausa entre
# chamadas) em vez de long-polling agressivo: isso reduz bastante a
# janela de conflito, mas não a elimina — é uma limitação conhecida
# desta arquitetura de "um bot só para todas as máquinas" sem um
# relay/servidor central.
def obter_atualizacoes(offset, timeout_segundos=2):
    try:
        resposta = requests.get(
            _url("getUpdates"),
            params={
                "offset": offset,
                "timeout": timeout_segundos,
            },
            timeout=timeout_segundos + 10,
        )

        if resposta.status_code == 409:
            # Outra instância está consumindo o mesmo bot neste
            # instante. Não é um erro fatal, só tenta de novo depois.
            return []

        resposta.raise_for_status()

        return resposta.json().get(
            "result",
            [],
        )

    except requests.RequestException as erro:
        print(
            f"[rede_jarvis] Falha ao consultar o Telegram: {erro}"
        )

        return []


# Baixa o conteúdo de um arquivo recebido (foto ou documento) a
# partir do file_id retornado pela API do Telegram.
def baixar_arquivo(file_id):
    try:
        resposta = requests.get(
            _url("getFile"),
            params={
                "file_id": file_id
            },
            timeout=15,
        )

        resposta.raise_for_status()

        caminho_remoto = resposta.json()["result"]["file_path"]

        url_download = (
            "https://api.telegram.org/file/"
            f"bot{config.TELEGRAM_BOT_TOKEN}/{caminho_remoto}"
        )

        resposta_arquivo = requests.get(
            url_download,
            timeout=60,
        )

        resposta_arquivo.raise_for_status()

        return resposta_arquivo.content

    except (requests.RequestException, KeyError) as erro:
        print(
            f"[rede_jarvis] Falha ao baixar arquivo do Telegram: {erro}"
        )

        return None
