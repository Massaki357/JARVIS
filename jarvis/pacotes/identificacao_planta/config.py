# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão dos demais pacotes
# isolados (rede_jarvis, casa_inteligente, delegacao_ia,
# admin_terminal).
from dotenv import load_dotenv

import os

load_dotenv()

# Chave de API gratuita obtida em my.plantnet.org (Settings > API
# key). Nunca fica hardcoded — sempre vem do .env.
PLANTNET_API_KEY = os.getenv(
    "PLANTNET_API_KEY"
)

# Flora/projeto onde o Pl@ntNet busca a espécie. "all" busca em
# todas as floras cadastradas — o mais amplo possível, já que não há
# como saber de antemão a região da planta fotografada pela câmera.
# Outras opções (floras regionais, ex: "weurope", "canada") existem
# na API — ver GET /v2/projects na documentação oficial se um dia
# for necessário restringir.
PROJETO_PLANTNET = os.getenv(
    "PLANTNET_PROJETO",
    "all",
)

# Tempo limite, em segundos, para a chamada HTTP ao Pl@ntNet.
TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "PLANTNET_TIMEOUT_SEGUNDOS",
        "15",
    )
)

# Quantidade de espécies candidatas retornadas por
# plantnet_client.identificar() — a API já devolve a lista ordenada
# por confiança decrescente; isso só limita quantas das primeiras
# são repassadas pro Jarvis falar.
QUANTIDADE_RESULTADOS = 3


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
def config_schema():
    return [
        {
            "nome": "PLANTNET_API_KEY",
            "rotulo": "Chave de API do Pl@ntNet (my.plantnet.org)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "PLANTNET_PROJETO",
            "rotulo": "Flora/projeto de busca (padrão: all)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PLANTNET_TIMEOUT_SEGUNDOS",
            "rotulo": "Tempo limite da chamada, em segundos (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
