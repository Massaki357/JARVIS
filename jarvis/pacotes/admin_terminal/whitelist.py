import json
import re

from . import config

_cache = None


def _carregar():
    global _cache

    if _cache is None:
        try:
            _cache = json.loads(
                config.ARQUIVO_WHITELIST.read_text(encoding="utf-8")
            )

        except (OSError, json.JSONDecodeError) as erro:
            print(
                "[admin_terminal] Falha ao carregar whitelist.json "
                f"— nenhum comando será tratado como automático até "
                f"isso ser corrigido: {erro}"
            )
            _cache = []

    return _cache


def recarregar():
    global _cache
    _cache = None


def corresponde(comando_normalizado):
    for entrada in _carregar():
        tipo = entrada.get("tipo")
        padrao = entrada.get("padrao", "")

        if tipo == "exato":
            if comando_normalizado == padrao:
                return True

        elif tipo == "prefixo":
            if not comando_normalizado.startswith(padrao):
                continue

            resto = comando_normalizado[len(padrao):]
            regex_resto = entrada.get("regex_resto", "")

            if regex_resto and re.fullmatch(regex_resto, resto):
                return True

    return False
