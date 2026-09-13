from dotenv import load_dotenv

import os

load_dotenv()

VOZ_LOCAL_MQTT_HOST = os.getenv(
    "VOZ_LOCAL_MQTT_HOST",
    "localhost",
)

# 1884, não 1883: é estrutural nesta máquina (docs/voz_local.md).
VOZ_LOCAL_MQTT_PORT = int(
    os.getenv(
        "VOZ_LOCAL_MQTT_PORT",
        "1884",
    )
)

VOZ_LOCAL_MQTT_USERNAME = os.getenv(
    "VOZ_LOCAL_MQTT_USERNAME"
)

VOZ_LOCAL_MQTT_PASSWORD = os.getenv(
    "VOZ_LOCAL_MQTT_PASSWORD"
)

VOZ_LOCAL_MQTT_TLS = (
    os.getenv(
        "VOZ_LOCAL_MQTT_TLS",
        "false",
    ).strip().lower()
    in ("true", "1", "sim")
)

TOPICO_ENTRADA = os.getenv(
    "VOZ_LOCAL_TOPICO_ENTRADA",
    "jarvis/audio/entrada",
)

TOPICO_TEXTO_SAIDA = os.getenv(
    "VOZ_LOCAL_TOPICO_TEXTO_SAIDA",
    "jarvis/texto/saida",
)

TOPICO_TEXTO_ENTRADA = os.getenv(
    "VOZ_LOCAL_TOPICO_TEXTO_ENTRADA",
    "jarvis/texto/entrada",
)

TOPICO_SAIDA = os.getenv(
    "VOZ_LOCAL_TOPICO_SAIDA",
    "jarvis/audio/saida",
)

TOPICO_ERRO = os.getenv(
    "VOZ_LOCAL_TOPICO_ERRO",
    "jarvis/audio/erro",
)

PROPRIEDADE_TEXTO_RESPOSTA = "texto"

TIMEOUT_TRANSCRICAO_SEGUNDOS = int(
    os.getenv(
        "VOZ_LOCAL_TIMEOUT_TRANSCRICAO_SEGUNDOS",
        "25",
    )
)

TIMEOUT_RESPOSTA_SEGUNDOS = int(
    os.getenv(
        "VOZ_LOCAL_TIMEOUT_RESPOSTA_SEGUNDOS",
        "40",
    )
)

TIMEOUT_CONEXAO_SEGUNDOS = 10

LIMIAR_PROB_FALA = float(
    os.getenv(
        "VOZ_LOCAL_LIMIAR_PROB_FALA",
        "0.5",
    )
)

TAXA_VAD = 16000

LIMIAR_VOZ = float(
    os.getenv(
        "VOZ_LOCAL_LIMIAR_VOZ",
        "0.12",
    )
)

SILENCIO_SEGUNDOS = float(
    os.getenv(
        "VOZ_LOCAL_SILENCIO_SEGUNDOS",
        "1.0",
    )
)

DURACAO_MINIMA_SEGUNDOS = 0.4

DURACAO_MAXIMA_SEGUNDOS = 30.0

BLOCOS_PRE_FALA = 5

BLOCOS_POS_FALA = 5

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
