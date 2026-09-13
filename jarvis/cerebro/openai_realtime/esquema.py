import json

from jarvis.servicos.agentes.ferramentas import (
    normalizar_esquema as _normalizar_no,
)


def converter_declaracao(declaracao):
    try:
        bruto = declaracao.to_json_dict()

    except Exception:
        return None

    nome = bruto.get("name")

    if not nome:
        return None

    parametros = bruto.get("parameters") or {
        "type": "object",
        "properties": {},
    }

    return {
        "type": "function",
        "name": nome,
        "description": bruto.get("description", ""),
        "parameters": _normalizar_no(parametros),
    }


def montar_ferramentas(
    declaracoes_nativas,
    pacotes_registrados,
    filtro=None,
):
    declaracoes = list(declaracoes_nativas)

    for pacote in pacotes_registrados:
        try:
            declaracoes.extend(pacote.obter_function_declarations())

        except Exception:
            continue

    if filtro is not None:
        declaracoes = filtro(declaracoes)

    ferramentas = []

    for declaracao in declaracoes:
        convertida = converter_declaracao(declaracao)

        if convertida:
            ferramentas.append(convertida)

    return ferramentas


def interpretar_argumentos(bruto):
    if isinstance(bruto, dict):
        return bruto

    try:
        argumentos = json.loads(bruto or "{}")

    except (json.JSONDecodeError, TypeError):
        return {}

    return argumentos if isinstance(argumentos, dict) else {}
