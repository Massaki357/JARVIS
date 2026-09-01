# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão dos demais pacotes
# isolados.
from dotenv import load_dotenv

import os

load_dotenv()

# Reaproveita a MESMA variável MISTRAL_API_KEY que já existia no
# .env do projeto (de uma tarefa anterior) — nunca cria uma segunda
# chave/nome pra mesma credencial.
MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY"
)

# Modelo de visão da Mistral usado como segunda opinião independente
# do Gemini para identificação de objeto genérico.
#
# O Pixtral (o antigo modelo de visão dedicado da Mistral, que era o
# pedido original aqui) está DESCONTINUADO — confirmado na
# documentação oficial de depreciação da Mistral:
# pixtral-12b-2409 foi retirado em 31/12/2025, pixtral-large-2411 em
# 31/05/2026. A capacidade de visão passou a fazer parte dos modelos
# generalistas atuais (Mistral Large/Medium/Small), não existe mais
# um modelo de visão dedicado separado no catálogo da Mistral.
# mistral-medium-latest foi uma escolha CONSCIENTE do usuário diante
# disso (substituto direto do antigo Pixtral Large segundo a própria
# doc de depreciação da Mistral) — não um default assumido sem
# checar. Ver CLAUDE.md para o histórico completo dessa decisão.
MODELO_MISTRAL_VISION = os.getenv(
    "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
    "mistral-medium-latest",
)

# Tempo limite, em segundos, para a chamada HTTP à Mistral.
TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
        "20",
    )
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
def config_schema():
    return [
        {
            "nome": "MISTRAL_API_KEY",
            "rotulo": "Chave de API da Mistral (segunda opinião visual)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
            "rotulo": "Modelo de visão da Mistral (padrão: mistral-medium-latest)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
            "rotulo": "Tempo limite da chamada, em segundos (padrão: 20)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
