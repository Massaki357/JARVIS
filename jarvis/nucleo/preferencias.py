# Lê config.json, na raiz do projeto, e expõe se a interrupção de
# fala por voz está ativa. Formato exato esperado:
#
#   {
#     "config": [
#       { "interrupcao": false }
#     ]
#   }
#
# Arquivo mínimo, de propósito único — ver docs/INTEGRATION.md, seção
# "Interrupção de fala (config.json)", pra reaplicar esse conceito em
# outro cliente sem precisar reler esta conversa.
import json

from jarvis.caminhos import CAMINHO_CONFIG_JSON

# Caminho vem de jarvis/caminhos.py — nunca calculado aqui, pra
# não depender de quantos níveis este arquivo está abaixo da raiz.
_CAMINHO_CONFIG = CAMINHO_CONFIG_JSON


def interrupcao_ativa():
    """
    Lê config[0]["interrupcao"] de config.json. Se o arquivo não
    existir, o campo estiver ausente, ou o JSON estiver em formato
    inesperado, retorna False (o comportamento padrão/atual — o
    microfone continua ignorado enquanto o jarvis fala) e avisa no
    console, sem nunca travar a inicialização do app por causa disso.
    """
    if not _CAMINHO_CONFIG.is_file():
        print(
            "Aviso: config.json não encontrado na raiz do projeto — "
            "usando interrupcao=False (padrão)."
        )
        return False

    try:
        with open(
            _CAMINHO_CONFIG,
            encoding="utf-8",
        ) as arquivo:
            dados = json.load(arquivo)

        return bool(
            dados["config"][0]["interrupcao"]
        )

    except json.JSONDecodeError as erro:
        print(
            f"Aviso: config.json com JSON inválido ({erro}) — "
            "usando interrupcao=False (padrão)."
        )
        return False

    except (
        KeyError,
        IndexError,
        TypeError,
    ):
        print(
            "Aviso: config.json não está no formato esperado "
            '(config[0]["interrupcao"]) — usando interrupcao=False '
            "(padrão)."
        )
        return False
