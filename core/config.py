import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# PROVEDOR DE IA ATIVO
# ============================================================
# Controla qual "cérebro" o ALFRED usa: "gemini" ou "openai".
# Para voltar ao Gemini depois dos testes, basta trocar o valor
# abaixo (ou definir PROVEDOR_IA=gemini no .env) e reiniciar o app.
# Nenhum outro arquivo precisa ser alterado.
PROVEDOR_IA = os.getenv("PROVEDOR_IA", "openai").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

# ============================================================
# CONFIGURAÇÃO DA OPENAI (Realtime API)
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Modelo Realtime usado pelo ALFRED quando PROVEDOR_IA = "openai".
OPENAI_REALTIME_MODEL = "gpt-realtime"

# ============================================================
# MODELOS REALTIME DISPONÍVEIS PARA TESTE
# ============================================================
#OPENAI_REALTIME_MODEL = "gpt-realtime"
#OPENAI_REALTIME_MODEL = "gpt-4o-realtime-preview"
#OPENAI_REALTIME_MODEL = "gpt-4o-mini-realtime-preview"

# Voz usada pelo ALFRED quando PROVEDOR_IA = "openai".
OPENAI_VOICE = "marin"

# ============================================================
# VOZES DISPONÍVEIS PARA TESTE (Realtime API)
# ============================================================
# alloy    - neutra
# ash      - grave
# ballad   - suave
# coral    - calorosa
# echo     - firme
# sage     - equilibrada
# shimmer  - brilhante
# verse    - versátil
# marin    - natural
# cedar    - natural/grave

# ============================================================
# CONFIGURAÇÃO DA TWELVE DATA (cotações e histórico de ações)
# ============================================================
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")