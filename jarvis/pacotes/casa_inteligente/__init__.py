from . import dispositivos_tuya

from google.genai import types


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


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "controlar_dispositivo_casa":
        return executar_acao(
            argumentos.get("dispositivo", ""),
            argumentos.get("acao", ""),
        )

    return None


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
