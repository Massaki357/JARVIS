# tuya-connector-python é o SDK oficial da Tuya para a Open API
# (TuyaOpenAPI cuida de autenticação, assinatura de requisição e
# renovação de token automaticamente).
from tuya_connector import TuyaOpenAPI

from . import config

# Uma única instância do cliente por processo — autentica na
# primeira chamada e reaproveita a sessão nas seguintes (o SDK
# renova o token sozinho quando necessário).
_cliente = None


def obter_cliente():
    global _cliente

    if _cliente is None:
        if (
            not config.TUYA_ACCESS_ID
            or not config.TUYA_ACCESS_SECRET
            or not config.TUYA_API_ENDPOINT
        ):
            raise RuntimeError(
                "TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / "
                "TUYA_API_ENDPOINT não configurados no .env."
            )

        cliente = TuyaOpenAPI(
            config.TUYA_API_ENDPOINT,
            config.TUYA_ACCESS_ID,
            config.TUYA_ACCESS_SECRET,
        )

        resposta = cliente.connect()

        if not resposta.get("success"):
            raise RuntimeError(
                f"Falha ao autenticar na Tuya: {resposta.get('msg')}"
            )

        _cliente = cliente

    return _cliente


# uid da conta autenticada — necessário para consultar os
# dispositivos vinculados via /v1.0/users/{uid}/devices.
def obter_uid():
    return obter_cliente().token_info.uid


def get(caminho, params=None):
    return obter_cliente().get(caminho, params)


def post(caminho, corpo=None):
    return obter_cliente().post(caminho, corpo)


# Envia uma lista de comandos DP para um dispositivo. comandos é uma
# lista de dicts {"code": ..., "value": ...}.
#
# Nunca lança exceção — sempre retorna (sucesso: bool, mensagem: str),
# pro Jarvis conseguir informar por voz o que aconteceu mesmo se algo
# falhar (dispositivo offline, credencial inválida, DP code errado,
# Data Center suspensa, etc).
def enviar_comando(device_id, comandos):
    try:
        resposta = post(
            f"/v1.0/devices/{device_id}/commands",
            {
                "commands": comandos
            },
        )

    except Exception as erro:
        return False, f"Falha ao falar com a Tuya: {erro}"

    if not resposta.get("success"):
        return False, resposta.get(
            "msg",
            "Erro desconhecido da API da Tuya.",
        )

    return True, "Comando enviado com sucesso."
