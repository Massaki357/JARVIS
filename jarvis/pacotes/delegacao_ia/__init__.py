from . import roteador

from google.genai import types


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="delegar_tarefa",
        description=(
            "Delega uma tarefa de texto pontual para outro provedor "
            "de IA. Use 'pergunta_rapida' para fatos objetivos, "
            "cálculo simples ou definição curta — algo sem várias "
            "etapas de raciocínio. Use 'resumo' para resumir um "
            "texto/conteúdo mais longo que o usuário forneceu ou que "
            "está no contexto da conversa. Use 'segunda_opiniao' "
            "SOMENTE em decisões de peso real, dinheiro ou risco "
            "significativo, onde vale o custo de uma IA "
            "independente conferindo — é cara, use raramente. Pra "
            "qualquer outra tarefa de raciocínio (planejamento, "
            "comparação, análise) sem risco real, responda com seu "
            "próprio raciocínio, sem chamar esta função. Se a "
            "delegação falhar ou estiver indisponível, responda a "
            "solicitação você mesmo, com seu próprio raciocínio, sem "
            "travar esperando nem repetir a tentativa."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tipo_tarefa": types.Schema(
                    type="STRING",
                    enum=[
                        "pergunta_rapida",
                        "resumo",
                        "segunda_opiniao",
                    ],
                    description=(
                        "Tipo da tarefa a delegar, conforme o "
                        "contexto da conversa — não peça isso ao "
                        "usuário, decida você mesmo. 'segunda_opiniao' "
                        "é rara e cara (OpenAI): só pra decisão de "
                        "peso real, dinheiro ou risco significativo."
                    ),
                ),
                "conteudo": types.Schema(
                    type="STRING",
                    description=(
                        "O texto a ser processado: a pergunta, o "
                        "conteúdo a resumir, ou a descrição do "
                        "problema a analisar."
                    ),
                ),
            },
            required=[
                "tipo_tarefa",
                "conteudo",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "delegar_tarefa":
        return roteador.delegar(
            argumentos.get("tipo_tarefa", ""),
            argumentos.get("conteudo", ""),
        )

    return None
