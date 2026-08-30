from . import config, notificacoes, telegram_client

import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt

LIMITE_TELEGRAM_BYTES = config.LIMITE_TELEGRAM_MB * 1024 * 1024


# ============================================================
# Envio (lado de quem manda o arquivo)
# ============================================================

# Implementa o envio de um arquivo local para outra máquina.
# argumentos precisa conter "caminho" (arquivo local) e
# "maquina_destino". Até LIMITE_TELEGRAM_MB, envia direto como
# documento; acima disso, usa o Google Drive como intermediário.
def enviar_arquivo(origem, argumentos):
    caminho = (argumentos or {}).get("caminho")
    maquina_destino = (argumentos or {}).get("maquina_destino")

    if not caminho or not maquina_destino:
        return "É necessário informar 'caminho' e 'maquina_destino'."

    caminho_arquivo = Path(caminho)

    if not caminho_arquivo.is_file():
        return f"Arquivo '{caminho}' não encontrado."

    tamanho = caminho_arquivo.stat().st_size

    if tamanho <= LIMITE_TELEGRAM_BYTES:
        legenda = json.dumps(
            {
                "token": config.TOKEN_REDE_JARVIS,
                "origem": config.NOME_MAQUINA,
                "destino": maquina_destino,
                "tipo": "arquivo",
            }
        )

        enviado = telegram_client.enviar_documento(
            config.TELEGRAM_CHAT_ID,
            str(caminho_arquivo),
            legenda,
        )

        if not enviado:
            return (
                f"Falha ao enviar '{caminho_arquivo.name}' pelo Telegram."
            )

        return (
            f"Arquivo '{caminho_arquivo.name}' enviado para "
            f"{maquina_destino}."
        )

    return _enviar_via_drive(
        caminho_arquivo,
        maquina_destino,
    )


def _enviar_via_drive(caminho_arquivo, maquina_destino):
    # Import tardio para evitar import circular (telegram_listener
    # também importa este módulo para tratar arquivos recebidos).
    from . import telegram_listener

    email_destino = telegram_listener.consultar_client_email(
        maquina_destino
    )

    if not email_destino:
        return (
            f"Não foi possível obter a Service Account de "
            f"'{maquina_destino}' para compartilhar o arquivo via Drive."
        )

    try:
        servico = _obter_servico_drive()

        from googleapiclient.http import MediaFileUpload

        arquivo_drive = servico.files().create(
            body={
                "name": caminho_arquivo.name
            },
            media_body=MediaFileUpload(
                str(caminho_arquivo)
            ),
            fields="id",
        ).execute()

        id_arquivo = arquivo_drive["id"]

        servico.permissions().create(
            fileId=id_arquivo,
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": email_destino,
            },
        ).execute()

    except Exception as erro:
        return (
            f"Falha ao enviar '{caminho_arquivo.name}' via Google "
            f"Drive: {erro}"
        )

    envelope = json.dumps(
        {
            "token": config.TOKEN_REDE_JARVIS,
            "origem": config.NOME_MAQUINA,
            "destino": maquina_destino,
            "tipo": "arquivo_drive",
            "id_arquivo_drive": id_arquivo,
            "nome_arquivo": caminho_arquivo.name,
        }
    )

    telegram_client.enviar_mensagem(
        config.TELEGRAM_CHAT_ID,
        envelope,
    )

    return (
        f"Arquivo '{caminho_arquivo.name}' enviado via Google Drive "
        f"para {maquina_destino} (maior que {config.LIMITE_TELEGRAM_MB}MB)."
    )


def _obter_servico_drive():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON não configurado no .env."
        )

    credenciais = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/drive"],
    )

    return build(
        "drive",
        "v3",
        credentials=credenciais,
    )


# Lê o client_email da credencial de Service Account desta máquina —
# usado para responder à consulta que outra máquina faz antes de
# compartilhar um arquivo grande via Drive.
def obter_client_email_local():
    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return None

    try:
        with open(
            config.GOOGLE_SERVICE_ACCOUNT_JSON,
            "r",
            encoding="utf-8",
        ) as arquivo:
            return json.load(arquivo).get("client_email")

    except (OSError, json.JSONDecodeError):
        return None


# ============================================================
# Recebimento (lado de quem recebe o arquivo)
# ============================================================

# Chamado pelo listener quando um documento chega direto pelo
# Telegram (arquivo dentro do limite).
def receber_arquivo(origem, nome_sugerido, conteudo):
    threading.Thread(
        target=_processar_recebimento,
        args=(origem, nome_sugerido, conteudo),
        daemon=True,
    ).start()


# Chamado pelo listener quando chega um aviso de arquivo grande via
# Drive: baixa o arquivo, processa o recebimento e depois apaga a
# cópia do Drive.
def baixar_e_receber_arquivo_drive(origem, id_arquivo, nome_arquivo):
    try:
        servico = _obter_servico_drive()
        conteudo = servico.files().get_media(
            fileId=id_arquivo
        ).execute()

    except Exception as erro:
        print(
            f"[rede_jarvis] Falha ao baixar arquivo do Drive: {erro}"
        )

        return

    _processar_recebimento(
        origem,
        nome_arquivo,
        conteudo,
    )

    try:
        servico.files().delete(
            fileId=id_arquivo
        ).execute()

    except Exception as erro:
        print(
            "[rede_jarvis] Falha ao apagar arquivo do Drive após o "
            f"download: {erro}"
        )


def _processar_recebimento(origem, nome_sugerido, conteudo):
    notificacoes.notificar_simples(
        f"Arquivo recebido de {origem}",
        f"Recebendo '{nome_sugerido}'. Escolha onde salvar.",
    )

    caminho_escolhido = _perguntar_onde_salvar(nome_sugerido)

    if caminho_escolhido is None:
        config.PASTA_TRANSFERENCIAS_PADRAO.mkdir(
            parents=True,
            exist_ok=True,
        )

        caminho_escolhido = (
            config.PASTA_TRANSFERENCIAS_PADRAO / nome_sugerido
        )

    try:
        Path(caminho_escolhido).write_bytes(conteudo)

    except OSError as erro:
        print(
            f"[rede_jarvis] Falha ao salvar arquivo recebido: {erro}"
        )


# ============================================================
# Ponte com a thread de UI (QFileDialog só pode rodar na thread do
# Qt, mas o pedido de salvar chega de uma thread de background do
# listener do Telegram). Sinais Qt são thread-safe: emitir de
# qualquer thread executa o slot conectado na thread onde o QObject
# receptor "mora" — desde que esse QObject tenha sido criado na
# thread principal, o que preparar_ponte_gui() garante.
# ============================================================

class _PonteSalvarArquivo(QObject):
    pedido_salvar = Signal(str, object)

    def __init__(self):
        super().__init__()

        self.pedido_salvar.connect(
            self._salvar,
            Qt.QueuedConnection,
        )

    def _salvar(self, nome_sugerido, contexto):
        from PySide6.QtWidgets import QFileDialog

        try:
            caminho, _ = QFileDialog.getSaveFileName(
                None,
                "Salvar arquivo recebido",
                str(Path.home() / nome_sugerido),
            )

            contexto["caminho"] = caminho or None

        finally:
            contexto["evento"].set()


_ponte = None


# Deve ser chamada a partir da thread principal (GUI) durante a
# inicialização do pacote, para que o QObject da ponte "nasça" na
# thread certa (ver rede_jarvis/__init__.py).
def preparar_ponte_gui():
    global _ponte

    if _ponte is None:
        _ponte = _PonteSalvarArquivo()


def _perguntar_onde_salvar(nome_sugerido):
    if _ponte is None:
        # preparar_ponte_gui() não foi chamada; usa o fallback
        # automático diretamente.
        return None

    contexto = {
        "caminho": None,
        "evento": threading.Event(),
    }

    _ponte.pedido_salvar.emit(
        nome_sugerido,
        contexto,
    )

    contexto["evento"].wait(
        timeout=config.TIMEOUT_TRANSFERENCIA_ARQUIVO
    )

    return contexto["caminho"]
