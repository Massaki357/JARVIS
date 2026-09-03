"""
Pesquisa invisível de informações atuais (DuckDuckGo, via ddgs).

Trazido do JARVIS COMPLETO (actions/web_search.py) e reembalado no
contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md. Não abre aba nenhuma e não rouba o foco do
usuário: o resultado volta como texto para o ALFRED responder por voz.

O ponto central do módulo é o filtro local de acoes.py
(avaliar_necessidade_pesquisa): antes de qualquer acesso à internet
ele decide, sem custo nenhum, se a pergunta realmente depende de dado
atual. Quando decide que não, despachar() devolve
resposta_sem_pesquisa(), que é uma instrução para o modelo responder
do próprio conhecimento — nunca uma busca silenciosa "por via das
dúvidas".

Diferente de delegacao_ia (que delega uma tarefa de texto para outro
LLM), aqui não há modelo nenhum envolvido: é busca na web, e só.
"""

# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import acoes

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

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
        # pesquisar_informacao_atual() já roda o filtro local por
        # dentro e devolve resposta_sem_pesquisa() quando a consulta
        # não precisa de dado atual — não duplicar essa decisão aqui.
        return acoes.pesquisar_informacao_atual(
            argumentos.get("consulta", "")
        )

    return None
