# Configuração do cérebro de voz LOCAL (o alfred-server rodando em
# Docker nesta mesma máquina). Mesma convenção dos pacotes: este
# módulo faz o próprio load_dotenv() em vez de importar
# jarvis/nucleo/config.py, para continuar sendo copiável isoladamente.
from dotenv import load_dotenv

import os

load_dotenv()

# ============================================================
# BROKER MQTT DO SERVIDOR LOCAL
# ============================================================
# ATENÇÃO: este NÃO é o mesmo broker do pacote rede_jarvis
# (jarvis/pacotes/rede_jarvis/), e a separação é obrigatória, não uma
# escolha de estilo. Aquele cliente aponta para um broker na nuvem
# (HiveMQ, porta 8883) e chama tls_set() incondicionalmente, além de
# configurar usuário/senha e um Last Will de presença. Um objeto do
# paho-mqtt é uma conexão para UM broker — não há como a mesma
# instância atender também um mosquitto em localhost:1883 sem TLS.
# Por isso aqui existe um cliente próprio (jarvis/cerebro/voz_local/mqtt_voz.py),
# seguindo o mesmo formato do de lá, sem alterar nada do rede_jarvis.
VOZ_LOCAL_MQTT_HOST = os.getenv(
    "VOZ_LOCAL_MQTT_HOST",
    "localhost",
)

# 1884, e NÃO 1883, por um motivo concreto desta máquina: existe um
# mosquitto NATIVO do Windows ligado a 127.0.0.1:1883 e ::1:1883. No
# Windows o bind específico ganha do curinga que o Docker usa, então
# todo connect em localhost:1883 caía no broker nativo — um broker
# vazio, sem o alfred-server — e as mensagens nunca chegavam ao
# servidor, que estava conectado e inscrito o tempo todo. O
# docker-compose.yml do alfred-server passou a publicar o broker na
# 1884 do host; dentro da rede do compose nada mudou.
VOZ_LOCAL_MQTT_PORT = int(
    os.getenv(
        "VOZ_LOCAL_MQTT_PORT",
        "1884",
    )
)

# Autenticação é opcional de propósito: o servidor hoje roda sem ela,
# mas deixar as duas variáveis prontas evita ter que mexer no código
# no dia em que o mosquitto ganhar usuário/senha.
VOZ_LOCAL_MQTT_USERNAME = os.getenv(
    "VOZ_LOCAL_MQTT_USERNAME"
)

VOZ_LOCAL_MQTT_PASSWORD = os.getenv(
    "VOZ_LOCAL_MQTT_PASSWORD"
)

# TLS desligado por padrão — um broker local em localhost não usa
# certificado. Só ligar se o servidor passar a exigir.
VOZ_LOCAL_MQTT_TLS = (
    os.getenv(
        "VOZ_LOCAL_MQTT_TLS",
        "false",
    ).strip().lower()
    in ("true", "1", "sim")
)

# ============================================================
# TÓPICOS
# ============================================================
# Convenção do servidor: o payload é o ARQUIVO INTEIRO, sem JSON e
# sem base64. Entrada e saída carregam áudio; o tópico de erro existe
# separado justamente porque uma mensagem de erro não pode vir
# misturada num tópico que carrega bytes de áudio.
# ETAPA 1 — transcrição: publica o áudio aqui...
TOPICO_ENTRADA = os.getenv(
    "VOZ_LOCAL_TOPICO_ENTRADA",
    "jarvis/audio/entrada",
)

# ...e a transcrição volta aqui, como JSON UTF-8
# {"texto":..., "tom":..., "sexo":...}. Texto cabe em JSON; nos
# tópicos de áudio o JSON só inflaria o payload, por isso os dois
# pares são separados.
TOPICO_TEXTO_SAIDA = os.getenv(
    "VOZ_LOCAL_TOPICO_TEXTO_SAIDA",
    "jarvis/texto/saida",
)

# ETAPA 2 — resposta falada: republica AQUI o mesmo JSON recebido de
# TOPICO_TEXTO_SAIDA, e só quando o roteamento decidiu que aquilo era
# conversa (se era ferramenta, esta etapa não é chamada neste turno).
# "tom" e "sexo" são opcionais para o servidor.
TOPICO_TEXTO_ENTRADA = os.getenv(
    "VOZ_LOCAL_TOPICO_TEXTO_ENTRADA",
    "jarvis/texto/entrada",
)

# ...e o WAV final volta aqui.
TOPICO_SAIDA = os.getenv(
    "VOZ_LOCAL_TOPICO_SAIDA",
    "jarvis/audio/saida",
)

# Tópico de erro ÚNICO para as duas metades — é assim no servidor, não
# existe um jarvis/texto/erro. A linha de texto vem prefixada pela
# metade que falhou ("transcrição: ..." ou "resposta: ..."), que é o
# que permite saber de qual pedido se trata.
TOPICO_ERRO = os.getenv(
    "VOZ_LOCAL_TOPICO_ERRO",
    "jarvis/audio/erro",
)

# Nome da user property (MQTT v5) que traz, ao lado do WAV de
# TOPICO_SAIDA, o TEXTO que o servidor acabou de falar.
#
# NÃO é configurável por .env de propósito, ao contrário dos tópicos
# acima: os tópicos são endereços, que cada instalação pode querer
# separar, mas este nome faz parte do formato da mensagem — combiná-lo
# errado com o servidor não daria erro nenhum, só um histórico
# silenciosamente pela metade. Um valor fixo nos dois lados é o que
# torna essa combinação impossível de errar. O servidor usa o mesmo
# nome no header HTTP equivalente (X-Resposta-Texto, em base64 lá
# porque header HTTP é latin-1; aqui a property já é UTF-8).
PROPRIEDADE_TEXTO_RESPOSTA = "texto"

# ============================================================
# TEMPOS DE ESPERA
# ============================================================
# Espera da ETAPA 1 (áudio -> texto). Só STT, então é a metade mais
# rápida das duas.
TIMEOUT_TRANSCRICAO_SEGUNDOS = int(
    os.getenv(
        "VOZ_LOCAL_TIMEOUT_TRANSCRICAO_SEGUNDOS",
        "25",
    )
)

# Espera da ETAPA 2 (texto -> WAV). Maior que a da etapa 1 de
# propósito: aqui roda o LLM e depois o TTS, não só o STT.
#
# Estourar qualquer um dos dois NÃO derruba a chamada: o erro aparece
# na interface e o microfone volta a escutar (ver cliente_local.py).
TIMEOUT_RESPOSTA_SEGUNDOS = int(
    os.getenv(
        "VOZ_LOCAL_TIMEOUT_RESPOSTA_SEGUNDOS",
        "40",
    )
)

# Tempo máximo esperando o CONNACK do broker ao abrir a chamada.
TIMEOUT_CONEXAO_SEGUNDOS = 10

# ============================================================
# DETECÇÃO DE FIM DE FALA (VAD por silêncio)
# ============================================================
# O Gemini Live e a Realtime API da OpenAI são streaming, com detecção
# de turno feita pelo SERVIDOR. O alfred-server é arquivo-entra /
# arquivo-sai, então quem decide onde a frase termina é este cliente.
#
# QUEM CLASSIFICA CADA BLOCO É O SILERO VAD, POR CONTEÚDO — não mais a
# amplitude. Ver jarvis/cerebro/voz_local/vad_silero.py para o porquê
# da troca; em resumo: amplitude não distingue fala de nada, então
# ruído de fundo contínuo e alto (moto, ventilador, música) mantinha
# todo bloco acima do limiar e a frase nunca fechava.
#
# Probabilidade de fala a partir da qual o bloco conta como fala. É
# uma probabilidade de 0 a 1 devolvida pelo modelo, NÃO um volume:
# aumentar isto não deixa o jarvis "mais surdo para sons baixos", deixa
# ele mais exigente quanto àquilo ser voz humana.
LIMIAR_PROB_FALA = float(
    os.getenv(
        "VOZ_LOCAL_LIMIAR_PROB_FALA",
        "0.5",
    )
)

# Taxa em que o modelo do VAD opera. NÃO é ajustável: a variante do
# modelo usada só aceita 16 kHz, que por sorte é exatamente a taxa em
# que este worker captura (TAXA_ENTRADA em cliente_local.py). Está
# aqui como constante nomeada para que os dois lugares que dependem
# disso digam por quê, em vez de repetir um 16000 solto.
TAXA_VAD = 16000

# LIMIAR DE AMPLITUDE — NÃO É MAIS USADO PELO VAD.
#
# Continua existindo por dois motivos: a animação da esfera segue
# baseada em calcular_nivel_audio (que é uma medida de volume mesmo, e
# está certa para isso), e o modo de emergência descrito abaixo cai
# nele quando o Silero não sobe. Se o VAD do Silero estiver
# funcionando, mexer aqui não muda nada — quem manda é
# LIMIAR_PROB_FALA.
LIMIAR_VOZ = float(
    os.getenv(
        "VOZ_LOCAL_LIMIAR_VOZ",
        "0.12",
    )
)

# Silêncio contínuo necessário para considerar a frase terminada.
SILENCIO_SEGUNDOS = float(
    os.getenv(
        "VOZ_LOCAL_SILENCIO_SEGUNDOS",
        "1.0",
    )
)

# Frases mais curtas que isto são descartadas como ruído (uma tosse,
# uma batida de tecla) em vez de virarem uma requisição ao servidor.
DURACAO_MINIMA_SEGUNDOS = 0.4

# Teto de segurança: uma frase nunca cresce sem limite (um ruído
# constante acima do limiar gravaria para sempre). Ao atingir este
# tempo a frase é fechada e enviada como está.
DURACAO_MAXIMA_SEGUNDOS = 30.0

# Blocos de áudio guardados ANTES do limiar ser cruzado, para não
# cortar a primeira sílaba (cada bloco tem ~64 ms a 16 kHz).
BLOCOS_PRE_FALA = 5

# Blocos de silêncio mantidos DEPOIS da última fala. O resto do
# silêncio que fechou a frase é aparado antes de publicar: sem isso,
# todo arquivo enviado carregaria SILENCIO_SEGUNDOS inteiros de nada
# no fim. Uma cauda pequena é mantida de propósito, porque cortar
# rente ao limiar come o fim da última palavra.
BLOCOS_POS_FALA = 5

# Teto do arquivo publicado no MQTT. Um WAV de 30 s a 16 kHz mono
# 16 bits tem ~960 KB, então 10 MB é folga larga — existe só para
# nunca empurrar algo absurdo para o broker.
LIMITE_ENVIO_MB = 10


def config_schema():
    return [
        {
            "nome": "VOZ_LOCAL_MQTT_HOST",
            "rotulo": "Host do broker MQTT do servidor local (padrão: localhost)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_MQTT_PORT",
            "rotulo": "Porta do broker MQTT local (padrão: 1883)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_MQTT_USERNAME",
            "rotulo": "Usuário do broker local (opcional — hoje sem autenticação)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_MQTT_PASSWORD",
            "rotulo": "Senha do broker local (opcional)",
            "sensivel": True,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_TIMEOUT_TRANSCRICAO_SEGUNDOS",
            "rotulo": (
                "Tempo máximo esperando a transcrição em "
                "jarvis/texto/saida, em segundos (padrão: 25)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_TIMEOUT_RESPOSTA_SEGUNDOS",
            "rotulo": (
                "Tempo máximo esperando o áudio da resposta em "
                "jarvis/audio/saida, em segundos (padrão: 40 — inclui "
                "LLM e TTS)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_LIMIAR_PROB_FALA",
            "rotulo": (
                "Detecção de fala: probabilidade mínima de o áudio ser voz "
                "humana, de 0 a 1 (padrão: 0.5 — diminua se ele não te "
                "ouvir, aumente se disparar com som que não é fala). NÃO é "
                "volume: ruído alto não abre a frase por ser alto"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_MODELO_VAD",
            "rotulo": (
                "Caminho de um arquivo .onnx do Silero VAD para usar no "
                "lugar do baixado automaticamente (opcional — em branco, "
                "ele se resolve sozinho na primeira chamada)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_LIMIAR_VOZ",
            "rotulo": (
                "Limiar de VOLUME, de 0 a 1 (padrão: 0.12). Só vale no modo "
                "de emergência, quando o modelo de detecção de fala não "
                "carrega — no funcionamento normal quem decide é "
                "VOZ_LOCAL_LIMIAR_PROB_FALA"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "VOZ_LOCAL_SILENCIO_SEGUNDOS",
            "rotulo": (
                "Silêncio necessário para fechar a frase e enviá-la, "
                "em segundos (padrão: 1.0)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
