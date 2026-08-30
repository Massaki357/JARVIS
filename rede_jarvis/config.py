# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

import os
from pathlib import Path

load_dotenv()

# Token do bot criado no @BotFather do Telegram. Compartilhado por
# todas as máquinas que rodam o jarvis.
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

# Segredo compartilhado entre todas as instâncias. Toda mensagem
# recebida do Telegram só é processada se contiver este token.
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

# Chat (grupo ou conversa privada com o bot) por onde circulam
# comandos, respostas e frames de todas as máquinas. A API do
# Telegram exige um chat_id de destino para enviar mensagens — esta
# variável não estava na lista original do pedido, mas é necessária
# para o bot saber para onde mandar cada mensagem. Todas as máquinas
# devem usar o mesmo chat_id (o bot precisa já ter recebido ao menos
# uma mensagem nesse chat para descobrir o ID).
TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
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
# antes de executar (ver rede_jarvis/permissoes.py).
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
# visualização local (1.5s) para respeitar o rate limit do Telegram
# (~1 mensagem/segundo) e a latência extra de upload/download.
INTERVALO_VISUALIZACAO_REMOTA = 2.5

# Timeout automático de segurança da visualização remota, em segundos
# — mesmo valor usado pela visualização contínua local.
TIMEOUT_VISUALIZACAO_REMOTA = 90

# Tamanho máximo, em MB, para enviar um arquivo diretamente pelo
# Telegram antes de usar o Google Drive como alternativa.
LIMITE_TELEGRAM_MB = 50

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
# quando um arquivo maior que LIMITE_TELEGRAM_MB precisa ser
# compartilhado via Drive).
TIMEOUT_CONSULTA_SERVICE_ACCOUNT = 15

# Log local simples (texto, sem banco de dados) de comandos remotos
# recebidos e executados.
ARQUIVO_LOG = (
    Path(__file__).resolve().parent / "comandos_remotos.log"
)
