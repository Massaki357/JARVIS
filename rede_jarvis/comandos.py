from vision.screen_capture import capturar_tela_bytes

from . import config, telegram_client, transferencia_arquivos, visualizacao_remota

import subprocess
import uuid

import psutil


# Captura um frame único da tela local e envia como foto pelo
# Telegram para quem pediu.
def _comando_capturar_tela(origem, argumentos):
    try:
        frame_bytes = capturar_tela_bytes()

    except Exception as erro:
        return f"Falha ao capturar a tela: {erro}"

    enviado = telegram_client.enviar_foto(
        config.TELEGRAM_CHAT_ID,
        frame_bytes,
        "Captura de tela solicitada.",
    )

    if not enviado:
        return "Tela capturada, mas houve falha ao enviar pelo Telegram."

    return "Tela capturada e enviada."


# Lista os nomes dos processos em execução (sem path completo/PID).
def _comando_listar_processos(origem, argumentos):
    nomes = set()

    for processo in psutil.process_iter(["name"]):
        try:
            nome = processo.info.get("name")

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        if nome:
            nomes.add(nome)

    if not nomes:
        return "Nenhum processo encontrado."

    return (
        "Processos em execução:\n"
        + "\n".join(sorted(nomes, key=str.lower))
    )


# Abre um aplicativo da whitelist configurada em config.WHITELIST_APPS
# — nunca um comando/caminho arbitrário vindo da mensagem.
def _comando_abrir_app(origem, argumentos):
    nome_app = (argumentos or {}).get("nome_app", "")

    if not isinstance(nome_app, str) or not nome_app.strip():
        return "Nome do aplicativo não informado."

    chave = nome_app.strip().lower()
    executavel = config.WHITELIST_APPS.get(chave)

    if not executavel:
        disponiveis = ", ".join(sorted(config.WHITELIST_APPS))

        return (
            f"Aplicativo '{nome_app}' não está na lista permitida. "
            f"Disponíveis: {disponiveis}."
        )

    try:
        subprocess.Popen([executavel])

    except OSError as erro:
        return f"Falha ao abrir '{nome_app}': {erro}"

    return f"Aplicativo '{nome_app}' aberto."


# Procura um arquivo pelo nome, só dentro das pastas permitidas em
# config.PASTAS_PERMITIDAS_BUSCA — nunca o disco inteiro.
def _comando_buscar_arquivo(origem, argumentos):
    termo = (argumentos or {}).get("termo", "")

    if not isinstance(termo, str) or not termo.strip():
        return "Termo de busca não informado."

    termo_normalizado = termo.strip().lower()
    encontrados = []

    for pasta in config.PASTAS_PERMITIDAS_BUSCA:
        if not pasta.exists():
            continue

        try:
            for caminho in pasta.rglob("*"):
                if (
                    caminho.is_file()
                    and termo_normalizado in caminho.name.lower()
                ):
                    encontrados.append(
                        f"{caminho.name} (em {caminho.parent})"
                    )

                    if len(encontrados) >= config.LIMITE_RESULTADOS_BUSCA:
                        break

        except OSError:
            continue

        if len(encontrados) >= config.LIMITE_RESULTADOS_BUSCA:
            break

    if not encontrados:
        return f"Nenhum arquivo encontrado para '{termo}'."

    return "Arquivos encontrados:\n" + "\n".join(encontrados)


# Envia um arquivo local desta máquina de volta para quem pediu.
def _comando_enviar_arquivo(origem, argumentos):
    argumentos_com_destino = dict(argumentos or {})
    argumentos_com_destino.setdefault(
        "maquina_destino",
        origem,
    )

    resultado = transferencia_arquivos.enviar_arquivo(
        origem,
        argumentos_com_destino,
    )

    return resultado


def _comando_iniciar_visualizacao_remota(origem, argumentos):
    id_sessao = str(uuid.uuid4())

    return visualizacao_remota.iniciar(
        origem,
        id_sessao,
    )


def _comando_parar_visualizacao_remota(origem, argumentos):
    return visualizacao_remota.parar(origem)


# Tabela de despacho — whitelist dos únicos comandos que o listener
# aceita executar (ver rede_jarvis/telegram_listener.py).
TABELA_COMANDOS = {
    "capturar_tela": _comando_capturar_tela,
    "listar_processos": _comando_listar_processos,
    "abrir_app": _comando_abrir_app,
    "buscar_arquivo": _comando_buscar_arquivo,
    "enviar_arquivo": _comando_enviar_arquivo,
    "iniciar_visualizacao_remota": _comando_iniciar_visualizacao_remota,
    "parar_visualizacao_remota": _comando_parar_visualizacao_remota,
}


def executar_comando(comando, origem, argumentos):
    funcao = TABELA_COMANDOS.get(comando)

    if not funcao:
        return f"Comando '{comando}' não é reconhecido."

    try:
        return funcao(origem, argumentos or {})

    except Exception as erro:
        return f"Erro ao executar '{comando}': {erro}"
