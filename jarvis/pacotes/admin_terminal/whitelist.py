# Carrega e consulta a lista de comandos aprovados para execução
# automática (jarvis/pacotes/admin_terminal/whitelist.json). O arquivo é a parte
# editável (você pode adicionar/remover entradas sem tocar em código
# Python) — este módulo só sabe interpretá-lo.
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


# Força reler whitelist.json do disco na próxima checagem — útil se o
# arquivo for editado manualmente com o app já em execução.
def recarregar():
    global _cache
    _cache = None


# Correspondência por padrão/prefixo LITERAL — nunca interpretação
# semântica do pedido. Para entradas "prefixo", o restante do comando
# (depois do prefixo) só é aceito se bater inteiro com regex_resto —
# isso impede que algo como 'winget upgrade --all & del /f /q C:\'
# seja aprovado só por começar com um prefixo válido.
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
