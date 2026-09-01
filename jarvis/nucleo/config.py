import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Controla se o gate de autenticação por palavra-chave (ver a seção
# "AUTENTICAÇÃO" de instrucao_sistema, em jarvis/gemini/cliente_live.py)
# é exigido dentro de uma chamada. Padrão True — o comportamento de
# segurança já existente nunca muda sozinho; só fica desativado se o
# usuário explicitamente colocar EXIGIR_AUTENTICACAO=false no .env.
EXIGIR_AUTENTICACAO = os.getenv(
    "EXIGIR_AUTENTICACAO",
    "true",
).strip().lower() not in ("false", "0", "nao", "não")

# Tempo, em segundos, sem atividade REAL (fala do ALFRED ou execução
# de uma função — nunca só ruído captado pelo microfone) durante uma
# chamada ativa antes de encerrá-la automaticamente. Ver
# GeminiLiveWorker.executar/timestamp_ultima_atividade em
# jarvis/gemini/cliente_live.py.
TIMEOUT_INATIVIDADE_SEGUNDOS = int(
    os.getenv(
        "TIMEOUT_INATIVIDADE_SEGUNDOS",
        "300",
    )
)


# Descreve as variáveis de .env deste módulo pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os
# campos automaticamente — mesmo contrato dos demais pacotes (ver
# docs/INTEGRATION.md, seção "Tela de configurações"), só que aqui em
# jarvis/nucleo/config.py em vez de jarvis/pacotes/<pacote>/config.py,
# já que este módulo não é um pacote de tools. Lacuna fechada: era
# anotado como "próximo passo natural, não esquecimento" — cobria só
# rede_jarvis/casa_inteligente/delegacao_ia/admin_terminal/etc, nunca
# a própria chave do Gemini. GEMINI_LIVE_MODEL/GEMINI_VOICE ficam de
# fora de propósito — são constantes Python fixas, não lidas de
# variável de ambiente nenhuma (ver o comentário logo abaixo delas:
# "swap the active value" em vez de virar uma variável de .env).
def config_schema():
    return [
        {
            "nome": "GEMINI_API_KEY",
            "rotulo": "Chave da API do Gemini (obrigatória para o app funcionar)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "EXIGIR_AUTENTICACAO",
            "rotulo": (
                "Exigir a palavra-chave de autenticação por voz "
                "(padrão: true — nunca desative sem entender o risco)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "TIMEOUT_INATIVIDADE_SEGUNDOS",
            "rotulo": (
                "Tempo sem atividade real antes de encerrar a "
                "chamada sozinho, em segundos (padrão: 300)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]

# Modelo usado pelo ALFRED
GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"

# ============================================================
# MODELOS DISPONÍVEIS PARA TESTE
# ============================================================
#MODELO = "gemini-2.5-flash-native-audio-preview-12-2025"
#MODELO = “gemini-2.5-flash-native-audio-preview-09-2025”
#MODELO = "gemini-3.1-flash-live-preview"


# Voz usada pelo ALFRED
GEMINI_VOICE = "Charon"

# ============================================================
# VOZES DISPONÍVEIS PARA TESTE
# ============================================================
#
# Zephyr   - brilhante
# Puck     - animada
# Charon   - informativa
# Kore     - feminia e firme
# Fenrir   - empolgada
# Leda     - jovem
# Orus     - firme
# Aoede    - leve
# Callirrhoe - descontraída
# Autonoe  - brilhante
# Enceladus - suave/sussurrante
# Iapetus  - clara
# Umbriel  - descontraída
# Algieba  - suave
# Despina  - suave
# Erinome  - clara
# Algenib  - rouca
# Rasalgethi - informativa
# Laomedeia - animada
# Achernar - suave
# Alnilam  - firme
# Schedar  - equilibrada
# Gacrux   - madura
# Pulcherrima - direta
# Achird   - amigável
# Zubenelgenubi - casual
# Vindemiatrix - feminina gentil
# Sadachbia - animada
# Sadaltager - experiente
# Sulafat  - calorosa