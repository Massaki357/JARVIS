"""
Sub-agente de ferramentas: o cérebro descreve o que o usuário quer,
este pacote descobre QUAL ferramenta atende e devolve as instruções
exatas de execução.

O PROBLEMA QUE ELE RESOLVE: custo. Um cérebro de voz paga o schema de
toda ferramenta declarada em TODO turno. Então o cérebro só tem
declarada uma lista curta de ferramentas diretas, e o resto é
descoberto sob demanda. O fluxo, na ordem:

  1. a função está na lista do cérebro? -> ler_instrucao_ferramenta
     (uma vez por conversa) e ele chama a função direto;
  2. não está?                          -> buscar_ferramenta (o
     sub-agente na Groq, que só enxerga as ocultas) e depois
     executar_ferramenta.

A lista direta e as instruções por ferramenta moram em
dados/perfis/<slug>/ferramentas_diretas/ — ver
jarvis/nucleo/perfis/ferramentas_diretas.py.

QUEM EXECUTA CONTINUA SENDO O CÉREBRO. Este pacote nunca despacha
nada: devolve texto. Isso é deliberado — despachar aqui criaria um
segundo caminho de execução de ferramentas no projeto (o roteamento
hierárquico já é um), e as travas de segurança de cada tool passariam
a depender de por qual caminho ela foi chamada.

NÃO CONFUNDIR COM jarvis/roteamento_hierarquico/. Aquele substitui o
raciocínio do cérebro: recebe a fala transcrita, escolhe a ferramenta
E a executa, para o cérebro de voz local, que não tem tool calling
nativo. Este aqui é o contrário — é uma ferramenta QUE O CÉREBRO
CHAMA, no meio do próprio raciocínio, e que devolve informação em vez
de ação. Os dois leem catálogos derivados das mesmas
FunctionDeclaration; nenhum dos dois tem lista própria.

Contrato padrão do projeto (docs/INTEGRATION.md):
obter_function_declarations() e despachar().
"""

# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import executor
from . import manual
from . import subagente

# As três tools deste pacote estão SEMPRE declaradas — são a porta de
# entrada para todo o resto — e por isso são pagas em TODO turno do
# cérebro de voz. As descrições delas são curtas de propósito: o fluxo
# completo (lista direta primeiro, sub-agente depois) já está explicado
# uma única vez na seção "SUAS FERRAMENTAS" do sistema.md do perfil, e
# repeti-lo aqui seria pagar o mesmo texto duas vezes por turno.
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
    """
    As instruções de uma ferramenta, para o cérebro ler antes de usá-la.

    O texto que volta é CURTO no cabeçalho de propósito: ele fica no
    histórico da chamada e é repago em todo turno seguinte, então cada
    palavra a mais aqui é multiplicada pelo resto da conversa.
    """
    nome = str(nome or "").strip()

    if not nome:
        return "Informe o nome da função da sua lista."

    # Um nome que não existe NUNCA pode receber "pode usar": o cérebro
    # chamaria uma função inexistente e perderia o turno.
    from jarvis.nucleo.perfis import catalogo_ferramentas

    try:
        existe = nome in catalogo_ferramentas.nomes_disponiveis()

    except Exception:
        existe = True

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
