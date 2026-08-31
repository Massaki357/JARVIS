from . import dispositivos_tuya

# Usado só para montar a FunctionDeclaration deste pacote — ver
# obter_function_declarations() logo abaixo. Mesmo padrão do
# rede_jarvis/__init__.py (ver INTEGRATION.md na raiz do projeto).
from google.genai import types


# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar(). O cliente
# Gemini Live só precisa conhecer essas duas funções.
#
# Diferente do rede_jarvis, este pacote não precisa de nenhum wiring
# extra (sem callbacks de sessão, sem inicialização em background) —
# cada ação é só uma chamada de API HTTP pontual.
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="controlar_dispositivo_casa",
        description=(
            "Use esta função somente quando o usuário pedir "
            "explicitamente para ligar ou desligar um dispositivo da "
            "casa inteligente (ex: 'liga o interruptor', 'desliga a "
            "tomada da sala', 'liga o ar condicionado'). O nome do "
            "dispositivo é resolvido automaticamente entre os "
            "dispositivos cadastrados — use exatamente o nome que o "
            "usuário falou, sem tentar adivinhar ou completar. Nunca "
            "use espontaneamente. Se não estiver claro qual "
            "dispositivo ou qual ação, pergunte antes de chamar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "dispositivo": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do dispositivo, conforme o usuário "
                        "falou (ex: 'interruptor', 'tomada da sala', "
                        "'ar condicionado')."
                    ),
                ),
                "acao": types.Schema(
                    type="STRING",
                    enum=[
                        "ligar",
                        "desligar",
                    ],
                    description="Ação a executar no dispositivo.",
                ),
            },
            required=[
                "dispositivo",
                "acao",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string). Se não reconhecer, retorna None.
def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "controlar_dispositivo_casa":
        return executar_acao(
            argumentos.get("dispositivo", ""),
            argumentos.get("acao", ""),
        )

    return None


# Resolve o dispositivo pelo nome falado (ver
# dispositivos_tuya.resolver_dispositivo) e executa a ação nele.
# Nunca lança exceção — sempre retorna uma mensagem clara, mesmo em
# caso de erro (dispositivo não encontrado, offline, falha da API).
def executar_acao(dispositivo, acao):
    if not dispositivo:
        return "Não entendi qual dispositivo você quer controlar."

    if acao not in ("ligar", "desligar"):
        return (
            f"Ação '{acao}' não é reconhecida. Use 'ligar' ou "
            "'desligar'."
        )

    candidato, erro = dispositivos_tuya.resolver_dispositivo(
        dispositivo
    )

    if erro:
        return erro

    if candidato["tipo"] == "switch":
        if acao == "ligar":
            return dispositivos_tuya.ligar(candidato["id"])

        return dispositivos_tuya.desligar(candidato["id"])

    if candidato["tipo"] == "infravermelho":
        if acao == "ligar":
            return dispositivos_tuya.ligar_infravermelho(
                candidato["infrared_id"],
                candidato["remote_id"],
                candidato["category_id"],
            )

        return dispositivos_tuya.desligar_infravermelho(
            candidato["infrared_id"],
            candidato["remote_id"],
            candidato["category_id"],
        )

    return (
        f"Tipo de dispositivo '{candidato['tipo']}' ainda não é "
        "suportado."
    )
