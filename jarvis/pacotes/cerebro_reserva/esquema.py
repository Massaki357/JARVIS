# Converte as FunctionDeclaration do Gemini (o formato que TODOS os
# pacotes deste projeto já expõem em obter_function_declarations())
# para o formato de "tools" da API estilo OpenAI, usado pela Mistral.
#
# Isto é o que faz o cérebro reserva herdar as ferramentas de graça:
# nenhuma descrição é reescrita à mão aqui. Um pacote novo, assim que
# entra em PACOTES_REGISTRADOS, passa a funcionar no modo reserva
# também, sem tocar em nada deste arquivo — e as regras de segurança
# que já estão escritas nas descrições originais (o "nunca escolha
# sozinho", o "só quando o usuário pedir explicitamente") continuam
# valendo, em vez de se perderem numa segunda cópia que envelheceria
# fora de sincronia.
import json

from . import config, ferramentas_locais


# O SDK do Gemini serializa o tipo como "OBJECT"/"STRING"/"ARRAY"; o
# esquema JSON usado pela OpenAI/Mistral espera minúsculas. A
# conversão é recursiva porque um parâmetro pode ter properties
# aninhadas e items de array.
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


# Uma FunctionDeclaration -> um dict de tool. Retorna None se a
# declaração vier em formato inesperado, para uma ferramenta
# malformada nunca derrubar o modo reserva inteiro.
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


# Todas as ferramentas de todos os pacotes registrados. A lista de
# pacotes é recebida por parâmetro, nunca importada de
# jarvis/gemini/cliente_live.py — é o cliente que importa este
# pacote, e o caminho inverso criaria import circular.
def montar_ferramentas(pacotes_registrados):
    # As nativas (memória, print, foto, encerrar) vêm primeiro, e são
    # declaradas à mão em ferramentas_locais.py porque as originais
    # moram dentro de executar() — ver o cabeçalho daquele arquivo.
    ferramentas = ferramentas_locais.obter_declaracoes()

    for pacote in pacotes_registrados:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            convertida = converter_declaracao(declaracao)

            if not convertida:
                continue

            # Ver config.FERRAMENTAS_EXCLUIDAS: algumas tools só fazem
            # sentido com a sessão Live viva.
            if (
                convertida["function"]["name"]
                in config.FERRAMENTAS_EXCLUIDAS
            ):
                continue

            ferramentas.append(convertida)

    return ferramentas


# Executa uma ferramenta pedida pelo modelo, percorrendo os pacotes
# na MESMA ordem do dispatch normal (ver processar_chamada_de_funcao
# em jarvis/gemini/cliente_live.py): o primeiro pacote que reconhece o
# nome responde, e despachar() devolve None quando não reconhece.
#
# Chamada de dentro de uma thread (o modo reserva é síncrono), então
# não precisa de asyncio.to_thread aqui — despachar() já é síncrona e
# pode bloquear à vontade.
def despachar_ferramenta(pacotes_registrados, nome, argumentos):
    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos or "{}")

        except json.JSONDecodeError:
            return (
                f"Os argumentos enviados para '{nome}' não eram um "
                "JSON válido. Peça ao usuário para repetir o pedido."
            )

    argumentos = argumentos or {}

    # Nativas primeiro — nenhum pacote usa esses nomes, mas manter a
    # ordem fixa evita que um pacote futuro passe a interceptá-los
    # sem querer.
    resultado_nativo = ferramentas_locais.despachar(nome, argumentos)

    if resultado_nativo is not None:
        return resultado_nativo

    for pacote in pacotes_registrados:
        try:
            resultado = pacote.despachar(nome, argumentos)

        except Exception as erro:
            return (
                f"A função '{nome}' falhou: {erro}. Avise o usuário "
                "e não tente executá-la de novo sozinho."
            )

        if resultado is not None:
            return resultado

    return (
        f"A função '{nome}' não está disponível no modo reserva. "
        "Explique isso ao usuário em uma frase curta."
    )
