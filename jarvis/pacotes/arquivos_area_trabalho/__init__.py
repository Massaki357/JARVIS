"""
Controle de arquivos e pastas da Área de Trabalho do Windows.

Trazido do JARVIS COMPLETO (actions/file_actions.py) e reembalado no
contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md. A lógica de acoes.py é a original, incluindo a
proteção central do módulo: TUDO passa por _esta_dentro_da_area /
_resolver_caminho_relativo, então nenhuma operação alcança um caminho
fora da Área de Trabalho.

Nenhuma função deste pacote exclui arquivo nenhum, e nenhuma
sobrescreve um item já existente.
"""

# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import acoes

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="criar_pasta_area_trabalho",
        description=(
            "Cria uma pasta nova na área de trabalho do Windows. "
            "Use quando o usuário pedir para criar uma pasta. "
            "Nunca sobrescreva nada."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description="Nome da pasta a ser criada.",
                )
            },
            required=["nome"],
        ),
    ),

    types.FunctionDeclaration(
        name="listar_area_de_trabalho",
        description=(
            "Lista os itens presentes na área de trabalho "
            "do Windows."
        ),
    ),

    types.FunctionDeclaration(
        name="organizar_area_de_trabalho_basico",
        description=(
            "Organiza arquivos soltos da área de trabalho "
            "em pastas por tipo, como Imagens, PDFs, "
            "Documentos e Compactados. Nunca exclui arquivos "
            "e nunca sobrescreve arquivos existentes."
        ),
    ),

    types.FunctionDeclaration(
        name="copiar_item_area_trabalho",
        description=(
            "Prepara um arquivo ou pasta da Área de Trabalho "
            "para ser copiado. Use quando o usuário disser copiar. "
            "Depois, use colar_item_area_trabalho quando ele indicar "
            "o destino. Nunca sobrescreve itens."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do arquivo ou pasta que será copiado."
                    ),
                ),
                "pasta_origem": types.Schema(
                    type="STRING",
                    description=(
                        "Pasta relativa dentro da Área de Trabalho. "
                        "Use vazio quando o item estiver diretamente "
                        "na Área de Trabalho."
                    ),
                ),
            },
            required=["nome"],
        ),
    ),

    types.FunctionDeclaration(
        name="recortar_item_area_trabalho",
        description=(
            "Prepara um arquivo ou pasta da Área de Trabalho "
            "para ser movido. Use quando o usuário disser recortar "
            "ou mover. Depois, use colar_item_area_trabalho quando "
            "ele indicar o destino. Nunca sobrescreve itens."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do arquivo ou pasta que será recortado."
                    ),
                ),
                "pasta_origem": types.Schema(
                    type="STRING",
                    description=(
                        "Pasta relativa dentro da Área de Trabalho. "
                        "Use vazio quando o item estiver diretamente "
                        "na Área de Trabalho."
                    ),
                ),
            },
            required=["nome"],
        ),
    ),

    types.FunctionDeclaration(
        name="colar_item_area_trabalho",
        description=(
            "Cola o último arquivo ou pasta preparado por copiar "
            "ou recortar. O destino deve ser uma pasta dentro da "
            "Área de Trabalho. Use destino vazio para colar na raiz "
            "da Área de Trabalho. Nunca sobrescreve itens."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pasta_destino": types.Schema(
                    type="STRING",
                    description=(
                        "Caminho relativo da pasta de destino dentro "
                        "da Área de Trabalho. Exemplo: Projetos/Cliente. "
                        "Use vazio para a raiz da Área de Trabalho."
                    ),
                ),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="renomear_item_area_trabalho",
        description=(
            "Renomeia um arquivo ou pasta existente dentro da "
            "Área de Trabalho. Use somente quando o usuário informar "
            "claramente o nome atual e o novo nome. Nunca sobrescreve."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome_atual": types.Schema(
                    type="STRING",
                    description="Nome atual do arquivo ou pasta.",
                ),
                "novo_nome": types.Schema(
                    type="STRING",
                    description="Novo nome desejado.",
                ),
                "pasta_origem": types.Schema(
                    type="STRING",
                    description=(
                        "Pasta relativa dentro da Área de Trabalho. "
                        "Use vazio quando o item estiver diretamente "
                        "na Área de Trabalho."
                    ),
                ),
            },
            required=[
                "nome_atual",
                "novo_nome",
            ],
        ),
    ),

    types.FunctionDeclaration(
        name="cancelar_transferencia_area_trabalho",
        description=(
            "Cancela o último copiar ou recortar que ainda não "
            "foi colado. Use quando o usuário pedir para cancelar "
            "a operação de arquivo."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "criar_pasta_area_trabalho":
        return acoes.criar_pasta_area_trabalho(
            argumentos.get("nome", "")
        )

    if nome_funcao == "listar_area_de_trabalho":
        return acoes.listar_area_de_trabalho()

    if nome_funcao == "organizar_area_de_trabalho_basico":
        return acoes.organizar_area_de_trabalho_basico()

    if nome_funcao == "copiar_item_area_trabalho":
        return acoes.copiar_item_area_trabalho(
            argumentos.get("nome", ""),
            argumentos.get("pasta_origem") or "",
        )

    if nome_funcao == "recortar_item_area_trabalho":
        return acoes.recortar_item_area_trabalho(
            argumentos.get("nome", ""),
            argumentos.get("pasta_origem") or "",
        )

    if nome_funcao == "colar_item_area_trabalho":
        return acoes.colar_item_area_trabalho(
            argumentos.get("pasta_destino") or ""
        )

    if nome_funcao == "renomear_item_area_trabalho":
        return acoes.renomear_item_area_trabalho(
            argumentos.get("nome_atual", ""),
            argumentos.get("novo_nome", ""),
            argumentos.get("pasta_origem") or "",
        )

    if nome_funcao == "cancelar_transferencia_area_trabalho":
        return acoes.cancelar_transferencia_area_trabalho()

    return None
