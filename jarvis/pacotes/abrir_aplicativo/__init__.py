"""
Abertura de aplicativos, programas e locais do Windows por voz.

Trazido do JARVIS COMPLETO (actions/app_actions.py) e reembalado no
contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md. SUBSTITUI o antigo pacote abrir_app_local (que
só conhecia o Get-StartApps e um cache em dados/apps_conhecidos.json):
esta versão resolve, em ordem, apelidos fixos do Windows (Meu
Computador, Explorador, Configurações, Calculadora, pastas pessoais,
Painel de Controle...), atalhos .lnk/.url do Menu Iniciar,
Get-StartApps (apps da Microsoft Store) e, por último, um dicionário
fixo de executáveis conhecidos resolvido com shutil.which.

Continua valendo a regra de sempre: nada é executado a partir de um
caminho ou comando vindo direto da fala — só o que uma dessas quatro
fontes já conhece nesta máquina, e executar_comando() sempre usa
subprocess.Popen(..., shell=False), nunca shell=True.
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
        name="abrir_aplicativo",
        description=(
            "Abre aplicativos, programas ou locais permitidos "
            "do Windows, como meu computador, explorador de "
            "arquivos, navegador, Google, Chrome, Edge, "
            "antivírus, Windows Defender, configurações ou "
            "painel de controle."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do aplicativo, programa "
                        "ou local a abrir."
                    ),
                )
            },
            required=["nome"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "abrir_aplicativo":
        return acoes.abrir_aplicativo(
            argumentos.get("nome", "")
        )

    return None
