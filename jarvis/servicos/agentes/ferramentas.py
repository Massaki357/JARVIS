"""
Conversão das ferramentas do projeto para o formato que o
bind_tools() do LangChain entende.

TODO pacote deste projeto declara suas tools como
types.FunctionDeclaration do SDK do Gemini (o contrato
obter_function_declarations() de docs/INTEGRATION.md). Isso não muda
com o LangChain: continua existindo UMA descrição por ferramenta, no
lugar onde ela sempre esteve, e é ela que vira tudo o mais.

O bind_tools() aceita dicionário de esquema JSON no formato da
OpenAI ({"type": "function", "function": {...}}), que é exatamente o
que jarvis/roteamento_hierarquico/esquema_groq.py já montava. A
lógica veio para cá inteira, porque agora ela não é mais "o
conversor da Groq": é o conversor de QUALQUER provedor alcançado
pela camada de agentes. O esquema_groq.py continua existindo e
reexporta daqui, para quem já o importava não precisar saber disso.

A normalização de tipo (o SDK do Gemini serializa "OBJECT"/"STRING"/
"ARRAY"; o esquema JSON espera minúsculas) MORA AQUI agora. Ela
nasceu em jarvis/cerebro/openai_realtime/esquema.py e era importada
de lá pelo conversor da Groq, mas passou a ser importada também por
esta camada — e aí virou um ciclo de importação real: agentes ->
cerebro.openai_realtime -> registro_pacotes -> delegacao_ia ->
agentes. O app não subia.

A solução é a mesma que já tinha sido usada para PACOTES_REGISTRADOS
quando ele saiu de dentro do cliente_live: lógica compartilhada por
dois lados não pode morar dentro de um deles. É lógica de esquema
JSON genérica, sem nada específico de Realtime nem de Groq, então o
lugar dela é aqui, e os dois conversores a importam daqui.
"""

import json


# O SDK do Gemini serializa o tipo como "OBJECT"/"STRING"/"ARRAY"; o
# esquema JSON usado por OpenAI, Groq, Cerebras e Mistral espera
# minúsculas. A conversão é recursiva porque um parâmetro pode ter
# properties aninhadas e items de array.
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
    """
    Uma FunctionDeclaration -> um dict de tool.

    Devolve None se a declaração vier em formato inesperado, para uma
    ferramenta malformada nunca derrubar o turno inteiro — mesma
    postura defensiva dos dois conversores que existiam antes.
    """
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
    """
    Os esquemas completos SÓ das ferramentas cujo nome está em
    nomes_candidatos — nunca das 45 de uma vez.

    Procura o nome em cada pacote, na ordem da lista (mesma convenção
    de despacho usada em todo o projeto: para no primeiro pacote que
    reconhece o nome).
    """
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
    """
    Os esquemas de TODAS as ferramentas registradas — usado só por
    jarvis/roteamento_hierarquico/medir_custo.py, para reconstruir o
    cenário monolítico original como referência de comparação. Nunca
    usado em operação normal.
    """
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
    """
    Os argumentos de uma chamada de ferramenta já chegam como dict no
    .tool_calls do LangChain, mas alguns provedores ainda entregam a
    string JSON crua. Um JSON inválido nunca deve derrubar o turno:
    vira dicionário vazio, e a própria função despachada devolve a
    mensagem de parâmetro faltando.
    """
    if isinstance(bruto, dict):
        return bruto

    try:
        argumentos = json.loads(bruto or "{}")

    except (json.JSONDecodeError, TypeError):
        return {}

    return argumentos if isinstance(argumentos, dict) else {}
