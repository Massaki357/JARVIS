import json

from jarvis.caminhos import CAMINHO_CONFIG_JSON

_CAMINHO_CONFIG = CAMINHO_CONFIG_JSON


def interrupcao_ativa():
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


def _ler_bloco():
    if not _CAMINHO_CONFIG.is_file():
        return {}

    try:
        with open(_CAMINHO_CONFIG, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        bloco = dados["config"][0]

        return bloco if isinstance(bloco, dict) else {}

    except (
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
        OSError,
    ):
        return {}


def ler_preferencia(chave, padrao=None):
    return _ler_bloco().get(chave, padrao)


def salvar_preferencia(chave, valor):
    bloco = _ler_bloco()
    bloco[chave] = valor

    temporario = _CAMINHO_CONFIG.with_suffix(".json.tmp")

    try:
        temporario.write_text(
            json.dumps(
                {"config": [bloco]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporario.replace(_CAMINHO_CONFIG)

        return True

    except OSError as erro:
        print(
            f"Aviso: não consegui gravar o config.json ({erro}) — "
            "a preferência vale só até fechar o app."
        )

        return False


def dispositivo_entrada():
    return str(_ler_bloco().get("microfone", "") or "").strip()


def dispositivo_saida():
    return str(_ler_bloco().get("alto_falante", "") or "").strip()


def prioridade_alta_ativa():
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
