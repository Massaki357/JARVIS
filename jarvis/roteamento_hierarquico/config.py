# Carrega as variáveis de ambiente do arquivo .env. Módulo próprio,
# com seu próprio load_dotenv() — mesmo padrão de duplicação por
# módulo já usado em jarvis/pacotes/delegacao_ia/config.py — em vez
# de importar as constantes de lá, para este módulo poder ser
# copiado/adaptado sozinho no futuro, se for parar no pipeline do
# servidor dedicado (STT/TTS em outra máquina).
from dotenv import load_dotenv

import os

load_dotenv()

# GROQ_API_KEY já existe no .env deste projeto (delegacao_ia já a
# lê) — aqui é só reaproveitada pela mesma variável, nunca duplicada
# com um nome diferente.
GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

# Timeout de cada chamada de completions, em segundos. Duas etapas
# significam duas chances de estourar — mantido curto, igual ao
# padrão já usado em delegacao_ia/config.py, pelo mesmo motivo: numa
# resposta por voz, é melhor desistir cedo do que travar esperando.
TIMEOUT_SEGUNDOS = 8

# Modelo usado em cada etapa do roteamento. Podem ser o mesmo modelo
# (padrão) ou modelos diferentes, cada um sobrescrevível por
# variável de ambiente própria. O default é o mesmo já usado em
# delegacao_ia (openai/gpt-oss-20b) por já estar confirmado
# funcionando neste projeto para chamadas de texto simples — MAS
# isso NÃO confirma que ele suporta "tools"/"tool_choice" da Groq
# (chamada de função), que é o que a etapa 2 precisa. Antes de usar
# isto em produção, confirmar ao vivo contra GET /v1/models e um
# teste real de tool-calling, mesma disciplina já documentada em
# delegacao_ia/config.py sobre nomes de modelo mudarem com
# frequência — nunca assumir que um nome de modelo continua
# suportando algo só porque suportava antes.
MODELO_GROQ_ETAPA1 = os.getenv(
    "ROTEAMENTO_MODELO_GROQ_ETAPA1",
    "openai/gpt-oss-20b",
)

MODELO_GROQ_ETAPA2 = os.getenv(
    "ROTEAMENTO_MODELO_GROQ_ETAPA2",
    "openai/gpt-oss-20b",
)

# Quantas ferramentas candidatas a etapa 1 pode apontar de uma vez.
# Acima disso, o roteador corta pelas 3 primeiras — nunca manda um
# schema completo de mais que isso pra etapa 2.
LIMITE_FERRAMENTAS_CANDIDATAS = 3


# Descreve as variáveis de .env deste módulo pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os
# campos automaticamente — regra do CLAUDE.md: todo módulo novo que
# lê .env precisa disso, mesmo fora de jarvis/pacotes/. GROQ_API_KEY
# não aparece aqui de novo: já é exibida na seção "Delegação de IA",
# e duas seções mostrando o mesmo campo sensível seria confuso sem
# necessidade.
def config_schema():
    return [
        {
            "nome": "ROTEAMENTO_MODELO_GROQ_ETAPA1",
            "rotulo": (
                "Modelo da etapa 1 — catálogo curto (padrão: "
                "openai/gpt-oss-20b)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "ROTEAMENTO_MODELO_GROQ_ETAPA2",
            "rotulo": (
                "Modelo da etapa 2 — schema completo (padrão: "
                "openai/gpt-oss-20b, precisa suportar tool-calling)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
