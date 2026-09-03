"""
Escrita de texto no campo que estiver ativo no Windows.

Trazido do JARVIS COMPLETO (actions/text_actions.py) e reembalado no
contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md.

O texto vai para a área de transferência REAL do Windows
(GlobalAlloc/SetClipboardData, formato CF_UNICODETEXT) e depois é
colado com um Ctrl+V simulado — preserva acento, cedilha e texto
longo muito melhor do que simular tecla por tecla. Isso significa que
o conteúdo anterior do clipboard do usuário é substituído; é o
comportamento original do curso e é o preço da confiabilidade aqui.

Limite de segurança de 10.000 caracteres, dentro de acoes.py.
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
        name="escrever_no_campo_ativo",
        description=(
            "Insere texto exatamente no campo de texto que estiver "
            "ativo no Windows, no local onde o cursor estiver piscando. "
            "Use somente quando o usuário pedir claramente para escrever, "
            "digitar, inserir ou colocar um texto no local selecionado. "
            "O parâmetro texto deve conter somente o conteúdo final que será "
            "inserido, sem introduções, aspas externas ou explicações. "
            "Não use esta função para responder perguntas normalmente por voz. "
            "Não use quando o usuário pedir para enviar uma mensagem, pois "
            "escrever e enviar são ações diferentes."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "texto": types.Schema(
                    type="STRING",
                    description=(
                        "Texto final exato que deve ser inserido "
                        "no campo ativo."
                    ),
                ),
            },
            required=["texto"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "escrever_no_campo_ativo":
        return acoes.escrever_no_campo_ativo(
            argumentos.get("texto", "")
        )

    return None
