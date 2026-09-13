import json


# Mora aqui para não fechar ciclo de import com cerebro.openai_realtime.
def normalizar_esquema(no):
    if not isinstance(no, dict):
        return no

    convertido = {}

    for chave, valor in no.items():
        if chave == "type" and isinstance(valor, str):
            convertido[chave] = valor.lower()

        elif chave == "properties" and isinstance(valor, dict):
            convertido[chave] = {
                nome: normalizar_esquema(sub)
                for nome, sub in valor.items()
            }

        elif chave == "items":
            convertido[chave] = normalizar_esquema(valor)

        else:
            convertido[chave] = valor

    return convertido


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
        "function": {
            "name": nome,
            "description": bruto.get("description", ""),
            "parameters": normalizar_esquema(parametros),
        },
    }


def obter_esquemas(nomes_candidatos, pacotes_registrados):
    candidatos_restantes = set(nomes_candidatos)
    esquemas = []

    for pacote in pacotes_registrados:
        if not candidatos_restantes:
            break

        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            if declaracao.name not in candidatos_restantes:
                continue

            convertido = converter_declaracao(declaracao)

            if convertido:
                esquemas.append(convertido)

            candidatos_restantes.discard(declaracao.name)

    return esquemas


def obter_todos_os_esquemas(pacotes_registrados):
    esquemas = []

    for pacote in pacotes_registrados:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            convertido = converter_declaracao(declaracao)

            if convertido:
                esquemas.append(convertido)

    return esquemas


def interpretar_argumentos(bruto):
    if isinstance(bruto, dict):
        return bruto

    try:
        argumentos = json.loads(bruto or "{}")

    except (json.JSONDecodeError, TypeError):
        return {}

    return argumentos if isinstance(argumentos, dict) else {}
