# Configuração do cérebro reserva — a IA que assume a conversa quando
# a sessão do Gemini Live falha. Lê o .env por conta própria, mesmo
# padrão dos outros pacotes isolados (rede_jarvis, casa_inteligente,
# delegacao_ia): nada é importado de jarvis/nucleo/config.py.
#
# A escolha de provedor por etapa NÃO é arbitrária — saiu de medição
# ao vivo das três chaves disponíveis (Groq, Cerebras, Mistral):
#
#   ouvir  -> Groq whisper-large-v3-turbo   0,70s   transcreveu pt-BR 100%
#   pensar -> Mistral mistral-small-latest  1,13s   50k tokens/min, 50 req/min
#   falar  -> SAPI local (voz Maria pt-BR)  0,10s   sem rede, sem custo
#
# Por que a Mistral pensa, e não a Groq (que é mais rápida, 0,63s):
# com as ferramentas do projeto inteiro no schema (~5k tokens por
# requisição), o limite de 8.000 tokens/minuto do free tier da Groq
# permite cerca de UMA pergunta por minuto — inviável para conversa.
# A Cerebras tem 30k tokens/min mas só 5 requisições/minuto, o que
# também trava (um turno com ferramenta custa 2 requisições). A
# Mistral tem 50k tokens/min E 50 req/min, ou seja ~10 turnos por
# minuto. Os limites foram lidos dos cabeçalhos x-ratelimit-* das
# próprias APIs, não estimados.
#
# A Groq continua sendo usada para OUVIR porque o limite de tokens de
# chat não se aplica ao Whisper (modelo separado, cota própria), e
# nesse papel ela é a mais rápida e a mais precisa em português.
import os

from dotenv import load_dotenv

load_dotenv()

# --- Chaves (reaproveitadas do que já existe no .env) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# --- Endpoints ---
URL_GROQ_TRANSCRICAO = (
    "https://api.groq.com/openai/v1/audio/transcriptions"
)
URL_MISTRAL_CHAT = "https://api.mistral.ai/v1/chat/completions"
URL_MISTRAL_FALA = "https://api.mistral.ai/v1/audio/speech"

# --- Modelos (confirmados ao vivo contra /v1/models de cada
# provedor; nomes de modelo mudam com frequência, então se algum
# começar a falhar com erro de modelo inexistente, consulte o
# endpoint de novo em vez de adivinhar um nome de memória) ---
MODELO_TRANSCRICAO = os.getenv(
    "RESERVA_MODELO_TRANSCRICAO",
    "whisper-large-v3-turbo",
)

MODELO_CEREBRO = os.getenv(
    "RESERVA_MODELO_CEREBRO",
    "mistral-small-latest",
)

# Só é usado quando RESERVA_USAR_VOZ_LOCAL=false. As vozes da Mistral
# são todas marcadas como en_us/en_gb, mas FALAM português
# corretamente — confirmado sintetizando uma frase em português e
# transcrevendo de volta com o Whisper (voltou idêntica). A etiqueta
# de idioma descreve a origem da voz, não uma limitação.
MODELO_FALA_MISTRAL = os.getenv(
    "RESERVA_MODELO_FALA",
    "voxtral-mini-tts-latest",
)

VOZ_MISTRAL = os.getenv("RESERVA_VOZ_MISTRAL", "en_paul_neutral")

# --- Voz local (SAPI do Windows) ---
# Padrão ligado: é 20x mais rápida que a TTS por rede (0,10s contra
# 2,0s), não gasta cota, e continua funcionando quando a rede está
# instável — que é justamente quando o Gemini tende a falhar e este
# pacote é acionado.
USAR_VOZ_LOCAL = os.getenv(
    "RESERVA_USAR_VOZ_LOCAL",
    "true",
).strip().lower() != "false"

# Trecho procurado na descrição das vozes SAPI instaladas. A desta
# máquina é "Microsoft Maria Desktop - Portuguese(Brazil)".
TRECHO_VOZ_LOCAL = os.getenv(
    "RESERVA_VOZ_LOCAL",
    "Portuguese",
)

# --- Captura de áudio (mesmos parâmetros do microfone da chamada
# normal, ver TAXA_ENTRADA/BLOCO em jarvis/gemini/cliente_live.py) ---
TAXA_AUDIO = 16000
BLOCO_AUDIO = 1024
CANAIS_AUDIO = 1

# Volume (RMS de amostras int16) acima do qual o bloco conta como
# fala. Silêncio de sala fica bem abaixo disso; ajustável se o
# microfone for muito sensível ou muito surdo.
LIMIAR_VOZ = float(os.getenv("RESERVA_LIMIAR_VOZ", "500"))

# Quanto tempo de silêncio encerra a fala do usuário.
SILENCIO_FIM_FALA_SEGUNDOS = 1.0

# Tempo máximo de uma única fala, para nunca gravar indefinidamente.
DURACAO_MAXIMA_FALA_SEGUNDOS = 30.0

# Quanto tempo esperar por alguém falar antes de desistir do turno e
# checar de novo se a chamada ainda deve continuar.
ESPERA_MAXIMA_SILENCIO_SEGUNDOS = 30.0

# --- Tempos limite de rede ---
TIMEOUT_TRANSCRICAO_SEGUNDOS = 30
TIMEOUT_CEREBRO_SEGUNDOS = 45
TIMEOUT_FALA_SEGUNDOS = 30

# Quanto esperar antes da única nova tentativa após um HTTP 429. A
# janela de limite da Mistral é por minuto, mas ela se renova de
# forma contínua, então alguns segundos costumam bastar — ver o
# tratamento de 429 em cerebro.py.
ESPERA_APOS_LIMITE_SEGUNDOS = 8

# Quantas rodadas de chamada de ferramenta um único turno pode fazer
# antes de o texto final ser exigido. Impede laço infinito de
# ferramenta caso o modelo insista em chamar função sem concluir.
MAXIMO_RODADAS_FERRAMENTA = 4

# Ferramentas que existem na chamada normal mas NÃO são oferecidas ao
# cérebro reserva. As duas listadas abrem janelas que injetam texto e
# arquivos dentro da sessão Live do Gemini — que, no modo reserva, é
# justamente a sessão que morreu. Oferecê-las seria oferecer um botão
# que não faz nada, e ainda gastaria ~830 caracteres de schema por
# requisição.
#
# Nota importante para quem for mexer aqui: NÃO reduza o consumo de
# tokens encurtando as descrições das outras ferramentas. Medido: as
# regras de segurança dentro delas ("nunca escolha sozinho",
# "pergunte ao usuário antes") ficam entre 68% e 95% do texto, ou
# seja, cortar o fim remove exatamente as salvaguardas e mantém só a
# parte que ensina a executar a ação.
FERRAMENTAS_EXCLUIDAS = {
    "abrir_chat",
    "abrir_envio_arquivo",
}

# Quantas mensagens do histórico são mantidas (fora a de sistema).
# Curto de propósito: cada turno já custa ~5k tokens de schema de
# ferramentas, então histórico longo consome a cota à toa.
MAXIMO_MENSAGENS_HISTORICO = 12


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os
# campos automaticamente. Ver docs/INTEGRATION.md, seção "Tela de
# configurações". Nenhuma é obrigatória: todas têm padrão funcional,
# e as duas chaves já são reaproveitadas de outros pacotes.
def config_schema():
    return [
        {
            "nome": "RESERVA_MODELO_CEREBRO",
            "rotulo": "Modelo do cérebro reserva (padrão: mistral-small-latest)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "RESERVA_MODELO_TRANSCRICAO",
            "rotulo": "Modelo de transcrição de voz (padrão: whisper-large-v3-turbo)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "RESERVA_USAR_VOZ_LOCAL",
            "rotulo": "Usar a voz do Windows em vez da voz por rede (true/false, padrão: true)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "RESERVA_VOZ_LOCAL",
            "rotulo": "Trecho do nome da voz do Windows (padrão: Portuguese)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "RESERVA_LIMIAR_VOZ",
            "rotulo": "Volume mínimo que conta como fala (padrão: 500)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
