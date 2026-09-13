from tuya_connector import TuyaOpenAPI

from . import config

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


def obter_uid():
    return obter_cliente().token_info.uid


def get(caminho, params=None):
    return obter_cliente().get(caminho, params)


def post(caminho, corpo=None):
    return obter_cliente().post(caminho, corpo)


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
