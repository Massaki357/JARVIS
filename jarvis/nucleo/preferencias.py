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


def prioridade_alta_ativa():
    """
    Lê config[0]["prioridade_alta"] de config.json. Ausente ou
    inválido = False (o padrão: prioridade normal, como sempre foi).

    Com True, o app pede ao Windows prioridade ACIMA DO NORMAL — ver
    aplicar_prioridade(). Serve para um jogo em tela cheia (que roda
    em prioridade alta) não tirar a vez das threads de áudio do
    jarvis. NÃO faz o app usar mais CPU ou memória: só muda a ordem
    da fila quando há disputa.
    """
    if not _CAMINHO_CONFIG.is_file():
        return False

    try:
        with open(
            _CAMINHO_CONFIG,
            encoding="utf-8",
        ) as arquivo:
            dados = json.load(arquivo)

        return bool(
            dados["config"][0]["prioridade_alta"]
        )

    except (
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ):
        return False


def aplicar_prioridade():
    """
    Aplica a prioridade acima do normal, se config.json pedir.

    Deliberadamente ACIMA_DO_NORMAL e não ALTA/TEMPO_REAL: as duas
    últimas podem deixar o resto do sistema (o jogo incluído)
    engasgado, o que seria trocar um problema por outro pior.

    Nunca levanta exceção nem bloqueia a inicialização: se psutil
    faltar ou o Windows recusar, só avisa no console e segue com a
    prioridade normal.
    """
    if not prioridade_alta_ativa():
        return False

    try:
        import psutil

        psutil.Process().nice(
            psutil.ABOVE_NORMAL_PRIORITY_CLASS
        )

        print(
            "[PRIORIDADE] Processo elevado para acima do normal "
            "(config.json: prioridade_alta)."
        )

        return True

    except Exception as erro:
        print(
            f"Aviso: não foi possível elevar a prioridade ({erro}) — "
            "seguindo com a prioridade normal."
        )

        return False
