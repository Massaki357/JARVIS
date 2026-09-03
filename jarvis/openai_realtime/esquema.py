"""
Converte as FunctionDeclaration do Gemini (o formato que TODOS os
pacotes deste projeto já expõem em obter_function_declarations()) para
o formato de "tools" da Realtime API da OpenAI.

É o que faz o provedor OpenAI herdar as ferramentas de graça:
nenhuma descrição é reescrita à mão aqui, então um pacote novo passa
a funcionar nos dois cérebros de voz assim que entra em
PACOTES_REGISTRADOS. As regras de segurança que moram dentro dessas
descrições ("nunca escolha sozinho", "só quando o usuário pedir
explicitamente") continuam valendo, em vez de se perderem numa
segunda cópia que envelheceria fora de sincronia.

Atenção ao formato de destino: a Realtime API usa
{"type", "name", "description", "parameters"} achatado, e NÃO o
formato de chat completions, que aninha tudo dentro de "function".
"""

import json


# O SDK do Gemini serializa o tipo como "OBJECT"/"STRING"/"ARRAY"; o
# esquema JSON usado pela OpenAI espera minúsculas. A conversão é
# recursiva porque um parâmetro pode ter properties aninhadas e items
# de array.
def _normalizar_no(no):
    if not isinstance(no, dict):
        return no

    convertido = {}

    for chave, valor in no.items():
        if chave == "type" and isinstance(valor, str):
            convertido[chave] = valor.lower()

        elif chave == "properties" and isinstance(valor, dict):
            convertido[chave] = {
                nome: _normalizar_no(sub)
                for nome, sub in valor.items()
            }

        elif chave == "items":
            convertido[chave] = _normalizar_no(valor)

        else:
            convertido[chave] = valor

    return convertido


# Uma FunctionDeclaration -> um dict de tool da Realtime API. Retorna
# None se a declaração vier em formato inesperado, para uma ferramenta
# malformada nunca derrubar a sessão inteira.
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


# Todas as ferramentas: as nativas do cliente (recebidas prontas, no
# mesmo formato de FunctionDeclaration usado pelo Gemini) seguidas das
# de cada pacote registrado.
def montar_ferramentas(declaracoes_nativas, pacotes_registrados):
    ferramentas = []

    for declaracao in declaracoes_nativas:
        convertida = converter_declaracao(declaracao)

        if convertida:
            ferramentas.append(convertida)

    for pacote in pacotes_registrados:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            convertida = converter_declaracao(declaracao)

            if convertida:
                ferramentas.append(convertida)

    return ferramentas


# Os argumentos chegam da Realtime API como uma STRING JSON. Um JSON
# inválido nunca deve derrubar a sessão: vira dicionário vazio, e a
# própria função devolve a mensagem de parâmetro faltando.
def interpretar_argumentos(bruto):
    if isinstance(bruto, dict):
        return bruto

    try:
        argumentos = json.loads(bruto or "{}")

    except (json.JSONDecodeError, TypeError):
        return {}

    return argumentos if isinstance(argumentos, dict) else {}
