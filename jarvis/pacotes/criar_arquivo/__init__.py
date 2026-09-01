# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import escritor

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="criar_arquivo",
        description=(
            "Cria um arquivo de texto simples com o conteúdo dado, "
            "numa das pastas permitidas desta máquina (Área de "
            "Trabalho, Documentos ou Downloads por padrão — nunca em "
            "qualquer outro lugar do disco). Use somente quando o "
            "usuário pedir explicitamente para criar, salvar ou "
            "gerar um arquivo de texto (ex: 'crie um arquivo com "
            "essa lista', 'salva isso num arquivo de texto na área "
            "de trabalho'). Não é pra documentos longos — o "
            "conteúdo é limitado a alguns milhares de caracteres e "
            "é truncado se passar disso. Se já existir um arquivo "
            "com o mesmo nome, NUNCA sobrescreve — cria um novo com "
            "um sufixo de data e hora."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do arquivo, sem extensão (ex: 'lista "
                        "de compras')."
                    ),
                ),
                "conteudo": types.Schema(
                    type="STRING",
                    description="Conteúdo de texto a ser gravado no arquivo.",
                ),
                "pasta": types.Schema(
                    type="STRING",
                    description=(
                        "Pasta onde criar o arquivo, exatamente como "
                        "o usuário falou (ex: 'área de trabalho', "
                        "'documentos', 'downloads'). Opcional — se "
                        "não informado, usa a pasta padrão "
                        "configurada."
                    ),
                ),
                "extensao": types.Schema(
                    type="STRING",
                    description=(
                        "Extensão do arquivo, sem o ponto (ex: "
                        "'txt', 'md'). Opcional, padrão 'txt'."
                    ),
                ),
            },
            required=[
                "nome",
                "conteudo",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "criar_arquivo":
        _sucesso, mensagem = escritor.criar_arquivo(
            argumentos.get("nome", ""),
            argumentos.get("conteudo", ""),
            argumentos.get("pasta") or None,
            argumentos.get("extensao") or "txt",
        )

        return mensagem

    return None
