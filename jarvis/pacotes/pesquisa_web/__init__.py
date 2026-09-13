from google.genai import types

from . import acoes


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="pesquisar_informacao_atual",
        description=(
            "Use esta função SOMENTE quando a pergunta exigir "
            "informação atual ou variável. Exemplos permitidos: "
            "cotação de moedas, jogos e placares, clima, notícias, "
            "preços atuais, resultados recentes, lançamentos, "
            "versões atuais e ocupantes atuais de cargos. "
            "NÃO use para definições, explicações, programação, "
            "matemática, biografias históricas ou conhecimentos "
            "estáveis. Exemplos proibidos: 'o que é Python?', "
            "'quem foi Albert Einstein?' e 'como funciona um motor?'. "
            "Na dúvida, responda sem pesquisar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "consulta": types.Schema(
                    type="STRING",
                    description=(
                        "Consulta curta e objetiva que contenha "
                        "o assunto atual, data, local ou equipe."
                    ),
                )
            },
            required=["consulta"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "pesquisar_informacao_atual":
        return acoes.pesquisar_informacao_atual(
            argumentos.get("consulta", "")
        )

    return None
