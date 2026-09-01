# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão dos demais pacotes
# isolados.
from dotenv import load_dotenv

import os

load_dotenv()

# Token do bot do Discord (Developer Portal > sua aplicação > Bot >
# Reset Token). Nunca fica hardcoded — sempre vem do .env.
#
# SETUP NECESSÁRIO NO DEVELOPER PORTAL (discord.com/developers),
# aba Bot da sua aplicação, seção "Privileged Gateway Intents":
#   - "MESSAGE CONTENT INTENT" — necessário pra ler conteúdo de
#     mensagens.
#   - "SERVER MEMBERS INTENT" — necessário pra listar/buscar membros
#     do servidor por nome (sem isso, buscar_membro() nunca encontra
#     ninguém, mesmo com o bot no servidor). Confirmado na
#     documentação oficial do discord.py antes de implementar: essa
#     intent é exigida tanto pra popular o cache local de membros
#     quanto pra Guild.fetch_members() (usado aqui).
# As duas intents também precisam ser ativadas no código (já feito
# em cliente.py) — ativar só no portal ou só no código não é
# suficiente, os dois lados são checados.
#
# Além disso, o bot precisa estar convidado pra pelo menos um
# servidor onde a pessoa que você quer mandar DM também esteja —
# buscar_membro() só enxerga quem está num servidor em comum com o
# bot.
DISCORD_BOT_TOKEN = os.getenv(
    "DISCORD_BOT_TOKEN"
)

# Tempo limite, em segundos, esperando a conexão com o Discord ficar
# pronta (on_ready) antes de desistir de uma operação.
TIMEOUT_CONEXAO_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_CONEXAO",
        "15",
    )
)

# Tempo limite, em segundos, para uma operação pontual (enviar DM)
# no loop do bot responder.
TIMEOUT_OPERACAO_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_OPERACAO",
        "15",
    )
)

# Tempo limite, em segundos, pra listar todos os membros de todos os
# servidores em que o bot está — pode demorar mais que uma operação
# pontual em servidores grandes.
TIMEOUT_LISTAGEM_MEMBROS_SEGUNDOS = int(
    os.getenv(
        "DISCORD_TIMEOUT_LISTAGEM_MEMBROS",
        "30",
    )
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
def config_schema():
    return [
        {
            "nome": "DISCORD_BOT_TOKEN",
            "rotulo": "Token do bot do Discord",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "DISCORD_TIMEOUT_CONEXAO",
            "rotulo": "Tempo limite de conexão, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DISCORD_TIMEOUT_OPERACAO",
            "rotulo": "Tempo limite por operação, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DISCORD_TIMEOUT_LISTAGEM_MEMBROS",
            "rotulo": "Tempo limite pra listar membros, em segundos (padrão: 30)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
