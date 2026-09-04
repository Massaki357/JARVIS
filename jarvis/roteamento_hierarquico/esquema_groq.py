# Converte as FunctionDeclaration do Gemini (o formato que TODOS os
# pacotes deste projeto já expõem em obter_function_declarations())
# para o formato de "tools" da API de Chat Completions da
# OpenAI/Groq — usado aqui na etapa 2 do roteamento hierárquico,
# depois que a etapa 1 já reduziu a lista a 1-3 ferramentas
# candidatas.
#
# Atenção ao formato de destino: Chat Completions ANINHA tudo dentro
# de "function" ({"type": "function", "function": {"name", ...}}) —
# diferente do formato ACHATADO que jarvis/openai_realtime/esquema.py
# usa pra Realtime API ({"type", "name", "description", "parameters"}
# direto). Por isso este é um conversor próprio, não uma reexportação
# do de lá.
#
# A normalização de tipo (o SDK do Gemini serializa "OBJECT"/
# "STRING"/"ARRAY"; o esquema JSON da OpenAI espera minúsculas) é a
# MESMA lógica recursiva nos dois casos — reaproveitada daqui em vez
# de duplicada, porque é lógica de schema JSON genérica, sem nada
# específico de Realtime.
import json

from jarvis.openai_realtime.esquema import _normalizar_no


# Uma FunctionDeclaration -> um dict de tool da Chat Completions.
# Retorna None se a declaração vier em formato inesperado, para uma
# ferramenta malformada nunca derrubar o turno inteiro — mesma
# postura defensiva do conversor da Realtime API.
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
            "parameters": _normalizar_no(parametros),
        },
    }


# Monta os schemas completos SÓ das ferramentas cujo nome está em
# nomes_candidatos — nunca das 45 de uma vez. Procura o nome em cada
# pacote de pacotes_registrados, na ordem da lista (mesma convenção
# de despacho já usada em toda parte do projeto: para no primeiro
# pacote que reconhece o nome).
def obter_schemas_completos(nomes_candidatos, pacotes_registrados):
    candidatos_restantes = set(nomes_candidatos)
    schemas = []

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
                schemas.append(convertido)

            candidatos_restantes.discard(declaracao.name)

    return schemas


# Monta os schemas de TODAS as ferramentas de pacotes_registrados —
# usado só por medir_custo.py, pra reconstruir o cenário monolítico
# original (todas as 45 de uma vez) como referência de comparação.
# Nunca usado pelo roteador em operação normal.
def obter_todos_os_schemas(pacotes_registrados):
    schemas = []

    for pacote in pacotes_registrados:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            convertido = converter_declaracao(declaracao)

            if convertido:
                schemas.append(convertido)

    return schemas


# Os argumentos de um tool_call da Chat Completions chegam como uma
# STRING JSON (igual à Realtime API). Um JSON inválido nunca deve
# derrubar o turno: vira dicionário vazio, e a própria função
# despachada devolve a mensagem de parâmetro faltando.
def interpretar_argumentos(bruto):
    if isinstance(bruto, dict):
        return bruto

    try:
        argumentos = json.loads(bruto or "{}")

    except (json.JSONDecodeError, TypeError):
        return {}

    return argumentos if isinstance(argumentos, dict) else {}
