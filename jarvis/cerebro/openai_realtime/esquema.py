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

# A normalização de tipo do esquema JSON ("OBJECT" -> "object", e
# assim por diante, recursivamente) nasceu neste arquivo, mas hoje
# mora em jarvis/servicos/agentes/ferramentas.py: ela é usada tanto
# aqui quanto pela camada de agentes, e deixá-la aqui dentro criava um
# ciclo de importação (agentes -> cerebro.openai_realtime ->
# registro_pacotes -> delegacao_ia -> agentes) que impedia o app de
# subir. Mesma lição de PACOTES_REGISTRADOS: o que dois lados usam não
# pode morar dentro de um deles.
#
# O nome local continua _normalizar_no para o resto deste arquivo não
# mudar.
from jarvis.servicos.agentes.ferramentas import (
    normalizar_esquema as _normalizar_no,
)


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
def montar_ferramentas(
    declaracoes_nativas,
    pacotes_registrados,
    filtro=None,
):
    """
    Converte as declarações (no formato do Gemini) para o formato da
    Realtime API.

    `filtro`, quando informado, recebe a lista COMPLETA de declarações
    e devolve o subconjunto que deve ir para a sessão — é assim que o
    perfil ativo entra aqui, sem este módulo precisar saber que
    perfis existem. Aplicado ANTES da conversão, de propósito:
    converter uma ferramenta para depois jogá-la fora seria trabalho
    à toa, e o filtro trabalha sobre os mesmos objetos que o cliente
    Gemini filtra, então a regra é literalmente a mesma nos dois
    provedores.
    """
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
