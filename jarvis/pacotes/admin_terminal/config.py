# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão de jarvis/pacotes/rede_jarvis/config.py e
# jarvis/pacotes/casa_inteligente/config.py (cada pacote isolado lê o .env sozinho).
from dotenv import load_dotenv

import os
from pathlib import Path

from jarvis.caminhos import PASTA_DADOS, PASTA_LOGS, garantir_pasta

load_dotenv()

# Nome da Tarefa Agendada do Windows usada para rodar comandos com
# privilégio de administrador sem pedir UAC a cada execução (ver
# jarvis/pacotes/admin_terminal/setup.py e jarvis/pacotes/admin_terminal/executor.py). Só existe
# depois que 'python -m jarvis.pacotes.admin_terminal.setup' for rodado manualmente.
NOME_TAREFA_AGENDADA = os.getenv(
    "ADMIN_TERMINAL_NOME_TAREFA",
    "JarvisAdminTerminal",
)

# Tempo limite padrão, em segundos, para um comando administrativo
# terminar. Comandos conhecidos por demorar mais (ex: dism
# /cleanup-image /restorehealth) devem pedir execucao_longa=True na
# tool em vez de mudar este padrão.
TIMEOUT_PADRAO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_PADRAO",
        "30",
    )
)

# Tempo limite usado quando a tool é chamada com execucao_longa=True.
TIMEOUT_COMANDO_LONGO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_LONGO",
        "300",
    )
)

# Tempo limite, em segundos, para o usuário confirmar (por voz ou
# clicando na notificação) um comando que não está na whitelist antes
# de negar automaticamente (fail-safe), mesmo padrão de
# rede_jarvis.config.TIMEOUT_PERMISSAO.
TIMEOUT_CONFIRMACAO_SEGUNDOS = int(
    os.getenv(
        "ADMIN_TERMINAL_TIMEOUT_CONFIRMACAO",
        "40",
    )
)

# Margem extra, em segundos, além do timeout do próprio comando, que
# executor.py espera pelo arquivo de resultado antes de desistir —
# cobre a latência do 'schtasks /run' iniciar o processo elevado.
MARGEM_ESPERA_TAREFA_SEGUNDOS = 10

PASTA_PACOTE = Path(__file__).resolve().parent

# Pasta usada para troca de arquivos (pedido/resultado) entre este
# processo (privilégio normal) e o processo elevado disparado pela
# Tarefa Agendada — ver jarvis/pacotes/admin_terminal/executor.py e
# jarvis/pacotes/admin_terminal/runner_elevado.py.
PASTA_FILA = garantir_pasta(PASTA_DADOS) / "admin_fila"

# Log local, texto simples, de todo comando administrativo executado
# (automático ou confirmado). Nunca apagado automaticamente pelo
# jarvis — ver jarvis/pacotes/admin_terminal/executor.py:registrar_log.
ARQUIVO_LOG = garantir_pasta(PASTA_LOGS) / "comandos_admin.log"

# Lista editável de padrões de comando aprovados para execução
# automática (sem confirmação) — ver jarvis/pacotes/admin_terminal/whitelist.py.
ARQUIVO_WHITELIST = PASTA_PACOTE / "whitelist.json"


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações". Nenhuma variável
# deste pacote é sensível ou obrigatória — todas têm um valor padrão
# funcional (ver os defaults acima).
def config_schema():
    return [
        {
            "nome": "ADMIN_TERMINAL_NOME_TAREFA",
            "rotulo": "Nome da Tarefa Agendada (padrão: JarvisAdminTerminal)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_PADRAO",
            "rotulo": "Tempo limite padrão por comando, em segundos (padrão: 30)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_LONGO",
            "rotulo": "Tempo limite para comandos de execução longa, em segundos (padrão: 300)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ADMIN_TERMINAL_TIMEOUT_CONFIRMACAO",
            "rotulo": "Tempo limite para confirmar um comando, em segundos (padrão: 40)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
