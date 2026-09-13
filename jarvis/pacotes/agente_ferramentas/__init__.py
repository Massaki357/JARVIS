from google.genai import types

from . import executor
from . import manual
from . import subagente

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="ler_instrucao_ferramenta",
        description=(
            "Devolve as instruções de uso de uma função da sua lista. "
            "Leia antes de usar a função pela primeira vez na conversa. "
            "Instrução para você, não para falar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description="Nome exato da função da sua lista.",
                ),
            },
            required=[
                "nome",
            ],
        ),
    ),
    types.FunctionDeclaration(
        name="buscar_ferramenta",
        description=(
            "Descobre qual ferramenta FORA da sua lista atende ao "
            "pedido, e como executá-la. Use só quando nenhuma função "
            "da sua lista servir. Instrução para você, não para falar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pedido": types.Schema(
                    type="STRING",
                    description=(
                        "A intenção do usuário em uma frase (ex: 'o "
                        "usuário quer criar um arquivo de texto')."
                    ),
                ),
            },
            required=[
                "pedido",
            ],
        ),
    ),
    types.FunctionDeclaration(
        name="executar_ferramenta",
        description=(
            "Executa a ferramenta que buscar_ferramenta indicou. Nunca "
            "use para uma função da sua lista."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description="Nome exato indicado por buscar_ferramenta.",
                ),
                "argumentos": types.Schema(
                    type="STRING",
                    description=(
                        "Parâmetros como JSON em texto, ou {} se não "
                        "houver."
                    ),
                ),
            },
            required=[
                "nome",
                "argumentos",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "ler_instrucao_ferramenta":
        return _ler_instrucao(argumentos.get("nome", ""))

    if nome_funcao == "buscar_ferramenta":
        return subagente.buscar(argumentos.get("pedido", ""))

    if nome_funcao == "executar_ferramenta":
        return executor.executar(
            argumentos.get("nome", ""),
            argumentos.get("argumentos", ""),
        )

    return None


def _ler_instrucao(nome):
    nome = str(nome or "").strip()

    if not nome:
        return "Informe o nome da função da sua lista."

    from jarvis.nucleo.perfis import catalogo_ferramentas

    try:
        existe = nome in catalogo_ferramentas.nomes_disponiveis()

    except Exception:
        existe = True

    # Nome inexistente nunca recebe 'pode usar'.
    if not existe:
        return (
            f"Não existe função {nome}. Confira o nome na sua lista, ou "
            "use buscar_ferramenta."
        )

    texto = manual.instrucao_completa(nome)

    if not texto:
        return (
            f"{nome} não tem instrução além da descrição que você já "
            "tem. Pode usar."
        )

    return f"Como usar {nome} (não leia em voz alta):\n{texto}"
