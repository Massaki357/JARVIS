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

# Tentativas por chamada quando a Groq responde 429 (rate limit).
# Não é para erro genérico: 429 é o único caso em que repetir tem
# sentido, porque o próprio servidor diz que a janela vai reabrir.
#
# Medido ao vivo neste projeto: o tier gratuito do openai/gpt-oss-20b
# tem teto de 8000 tokens por MINUTO, e cada chamada da etapa 1 custa
# ~1450 tokens (o catálogo inteiro vai no prompt toda vez) — ou seja,
# ~5 turnos por minuto antes de estourar, o que um ritmo normal de
# conversa ultrapassa fácil. O corpo do 429 vem com "Please try again
# in 975ms" e o cabeçalho retry-after, então a janela reabre em ~1s:
# repetir resolve, esperar o usuário repetir a frase não.
TENTATIVAS_RATE_LIMIT = 3

# Tentativas quando a Groq responde 400 porque o MODELO emitiu uma
# chamada de ferramenta numa etapa que não declarou ferramenta alguma
# ("Tool choice is none, but model called a tool"). É o único 4xx que
# vale repetir: o resultado varia entre chamadas idênticas, então a
# tentativa seguinte quase sempre traz o texto esperado. Ver
# roteador._e_chamada_de_ferramenta_indevida.
#
# 2, e não mais, POR CAUSA DO TETO DE TOKENS. Cada tentativa da etapa 1
# custa ~1,8k tokens contra os 8000 TPM do tier gratuito, então repetir
# à toa troca um erro por outro: numa medição de 5 turnos com 3
# tentativas, o único que falhou foi por 429 — esgotou o orçamento de
# rate limit que as repetições ajudaram a consumir.
#
# Duas basta porque a repetição é só a primeira linha de defesa: quem
# de fato resolve é o plano B da etapa 1 (refazer sem o histórico, que
# é o gatilho medido), e ele ainda é MAIS BARATO que uma repetição
# normal, por não reenviar o histórico. Ver
# roteador._e_chamada_de_ferramenta_indevida e processar_turno.
TENTATIVAS_TOOL_CALL_INDEVIDA = 2

# Espera base entre tentativas, em segundos, quando o servidor NÃO
# manda retry-after. Cresce a cada tentativa (1s, 2s, 4s...). Quando
# ele manda, o valor dele é respeitado — ninguém adivinha melhor que o
# próprio servidor quando a janela reabre.
ESPERA_BASE_RATE_LIMIT = 1.0

# Teto da espera de uma tentativa. Existe porque retry-after é
# controlado pelo servidor: um valor absurdo travaria o turno de voz
# por muito mais tempo do que vale a pena esperar falando.
ESPERA_MAXIMA_RATE_LIMIT = 5.0

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
