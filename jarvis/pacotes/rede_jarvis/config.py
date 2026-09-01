# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

import os
from pathlib import Path

from jarvis.caminhos import PASTA_LOGS, garantir_pasta

load_dotenv()

# A camada de transporte usa MQTT (protocolo padrão de pub/sub para
# IoT/automação), via um broker na nuvem (ex: HiveMQ Cloud). Chegamos
# aqui depois de duas tentativas com Telegram que não funcionaram por
# restrições da própria plataforma (ver histórico do projeto) — MQTT
# não tem esse tipo de pegadinha: qualquer máquina publica em um
# tópico e qualquer outra inscrita nele recebe, sem intermediário
# proprietário no meio.
#
# Todas as máquinas usam o MESMO broker/usuário/senha (credenciais do
# broker) — o que diferencia cada máquina é só o NOME_MAQUINA usado
# para filtrar o campo "destino" de cada mensagem.
MQTT_HOST = os.getenv(
    "MQTT_HOST"
)

MQTT_PORT = int(
    os.getenv(
        "MQTT_PORT",
        "8883",
    )
)

MQTT_USERNAME = os.getenv(
    "MQTT_USERNAME"
)

MQTT_PASSWORD = os.getenv(
    "MQTT_PASSWORD"
)

# Segredo compartilhado entre todas as instâncias. Toda mensagem
# recebida do MQTT só é processada se contiver este token.
TOKEN_REDE_JARVIS = os.getenv(
    "TOKEN_REDE_JARVIS"
)

# Identificador desta instância (ex: "casa", "loja"). Usado tanto para
# identificar origem/destino dos comandos quanto nas notificações e
# confirmações por voz.
NOME_MAQUINA = os.getenv(
    "NOME_MAQUINA",
    "maquina-sem-nome",
)

# Pasta local usada para salvar arquivos recebidos quando ninguém
# responde à notificação/diálogo de salvar dentro do timeout.
PASTA_TRANSFERENCIAS_PADRAO = Path(
    os.getenv(
        "PASTA_TRANSFERENCIAS_PADRAO",
        str(Path.home() / "Downloads" / "JarvisRecebidos"),
    )
)

# Caminho para o arquivo de credencial da Service Account do Google
# Drive desta máquina. Cada máquina tem a sua própria, não uma conta
# pessoal compartilhada.
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON"
)

# Se True, todo comando remoto recebido aguarda confirmação local
# antes de executar (ver jarvis/pacotes/rede_jarvis/permissoes.py).
PEDIR_PERMISSAO = (
    os.getenv(
        "PEDIR_PERMISSAO",
        "true",
    ).strip().lower()
    == "true"
)

# ============================================================
# Whitelist de aplicativos que podem ser abertos remotamente via
# abrir_app. Só executáveis conhecidos, resolvidos via PATH do
# Windows — nunca um comando arbitrário vindo da mensagem. Adicione
# outras entradas com o caminho completo do executável/atalho, se
# necessário.
# ============================================================
WHITELIST_APPS = {
    "bloco de notas": "notepad.exe",
    "calculadora": "calc.exe",
    "explorador de arquivos": "explorer.exe",
    "paint": "mspaint.exe",
}

# Pastas onde buscar_arquivo tem permissão de procurar — nunca o
# disco inteiro.
PASTAS_PERMITIDAS_BUSCA = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]

# Quantidade máxima de resultados retornados por buscar_arquivo.
LIMITE_RESULTADOS_BUSCA = 15

# Intervalo entre frames da visualização remota. Maior que o da
# visualização local (1.5s) pela latência extra de rede
# (upload/download pelo broker MQTT).
INTERVALO_VISUALIZACAO_REMOTA = 2.5

# Timeout automático de segurança da visualização remota, em segundos
# — mesmo valor usado pela visualização contínua local.
TIMEOUT_VISUALIZACAO_REMOTA = 90

# Tamanho máximo, em MB, para enviar um arquivo diretamente pelo MQTT
# antes de usar o Google Drive como alternativa. O limite real do
# broker é 5MB; fica um pouco abaixo por segurança (overhead do
# protocolo/propriedades MQTT5 usadas para carregar os metadados).
LIMITE_MQTT_MB = 4.5

# Timeout, em segundos, para responder ao diálogo de "onde salvar" um
# arquivo recebido antes de usar PASTA_TRANSFERENCIAS_PADRAO.
TIMEOUT_TRANSFERENCIA_ARQUIVO = 60

# Timeout, em segundos, para o usuário responder (por notificação ou
# por voz) a um pedido de permissão de comando remoto. Ao estourar,
# o pedido é negado por padrão (fail-safe).
TIMEOUT_PERMISSAO = 40

# Timeout, em segundos, que quem envia um comando remoto espera pela
# resposta da máquina destino.
TIMEOUT_RESPOSTA_COMANDO = 15

# Timeout, em segundos, para a máquina destino responder qual é o
# client_email da sua Service Account do Google Drive (usado só
# quando um arquivo maior que LIMITE_MQTT_MB precisa ser
# compartilhado via Drive).
TIMEOUT_CONSULTA_SERVICE_ACCOUNT = 15

# Log local simples (texto, sem banco de dados) de comandos remotos
# recebidos e executados. Nunca girado em vários arquivos nem apagado
# por completo — só aparado (mantém a metade mais recente) quando
# passa de LIMITE_TAMANHO_LOG_BYTES, pra nunca crescer sem limite —
# ver jarvis/pacotes/rede_jarvis/mqtt_listener.py:_registrar_log.
ARQUIVO_LOG = (
    garantir_pasta(PASTA_LOGS) / "comandos_remotos.log"
)

# Tamanho máximo, em bytes, antes de _registrar_log aparar o log —
# mesmo valor e mesma técnica de jarvis/pacotes/admin_terminal/config.py
# (pacotes isolados, cada um com sua própria cópia da constante, por
# convenção do projeto).
LIMITE_TAMANHO_LOG_BYTES = 5 * 1024 * 1024


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
def config_schema():
    return [
        {
            "nome": "MQTT_HOST",
            "rotulo": "Host do broker MQTT",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "MQTT_PORT",
            "rotulo": "Porta do broker MQTT",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MQTT_USERNAME",
            "rotulo": "Usuário do broker MQTT",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "MQTT_PASSWORD",
            "rotulo": "Senha do broker MQTT",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "TOKEN_REDE_JARVIS",
            "rotulo": "Token compartilhado entre as máquinas",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "NOME_MAQUINA",
            "rotulo": "Nome desta máquina",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PASTA_TRANSFERENCIAS_PADRAO",
            "rotulo": "Pasta padrão para arquivos recebidos",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "GOOGLE_SERVICE_ACCOUNT_JSON",
            "rotulo": "Caminho da credencial do Google Drive (arquivos grandes)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PEDIR_PERMISSAO",
            "rotulo": "Pedir permissão antes de executar comando remoto (true/false)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
