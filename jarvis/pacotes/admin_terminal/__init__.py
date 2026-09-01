from . import confirmacao, config, executor, politica

# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão de rede_jarvis, casa_inteligente e delegacao_ia (ver
# docs/INTEGRATION.md).
from google.genai import types

# Callback usado para o Jarvis anunciar por voz, de forma espontânea,
# o resultado de um comando confirmado pela notificação do Windows
# (nunca pela confirmação por voz — nesse caso o resultado já volta
# como resposta normal da tool, ver despachar()). Registrado uma vez
# pelo cliente Gemini Live via iniciar_admin_terminal() — ver
# docs/INTEGRATION.md, seção "Wiring extra por pacote".
_callback_falar = None


# Wiring extra deste pacote (além do contrato padrão
# obter_function_declarations()/despachar()) — ver docs/INTEGRATION.md.
# Precisa ser chamado uma vez, do __init__ do worker/cliente, com o
# mesmo callback_falar genérico já usado por rede_jarvis (o worker
# reaproveita o próprio método, não é um novo mecanismo).
def iniciar_admin_terminal(callback_falar=None):
    global _callback_falar
    _callback_falar = callback_falar


# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="executar_comando_admin",
        description=(
            "Executa um comando de terminal do Windows com "
            "privilégio de administrador nesta máquina. Use somente "
            "quando o usuário pedir explicitamente uma ação "
            "administrativa ou de manutenção do sistema (ex: "
            "'atualiza todos os programas', 'roda o scan do "
            "Windows', 'limpa o cache de DNS'). Monte o comando "
            "exato de terminal correspondente ao pedido — nunca "
            "invente um comando que o usuário não pediu, e nunca "
            "encadeie múltiplos comandos numa só chamada (nada de "
            "&&, |, ; dentro do comando). Se o comando estiver numa "
            "pequena lista de aprovação automática, ele roda direto "
            "e você já recebe o resultado. Senão, esta função NÃO "
            "executa nada — ela retorna uma instrução pedindo pra "
            "você perguntar ao usuário se confirma, e então chamar "
            "confirmar_comando_admin com a resposta dele."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "comando": types.Schema(
                    type="STRING",
                    description=(
                        "O comando de terminal exato a executar (ex: "
                        "'winget upgrade --all', 'sfc /scannow', "
                        "'ipconfig /flushdns'). Um único comando, "
                        "sem encadeamento."
                    ),
                ),
                "execucao_longa": types.Schema(
                    type="BOOLEAN",
                    description=(
                        "Verdadeiro somente se este comando é "
                        "conhecido por demorar mais que alguns "
                        "segundos (ex: 'dism /online /cleanup-image "
                        "/restorehealth'). Usa um tempo limite maior "
                        "para não cortar a execução cedo demais. "
                        "Padrão: falso."
                    ),
                ),
            },
            required=[
                "comando",
            ],
        ),
    ),
    types.FunctionDeclaration(
        name="confirmar_comando_admin",
        description=(
            "Use esta função somente logo depois de você ter "
            "perguntado ao usuário se confirma um comando "
            "administrativo pendente (a instrução veio no retorno "
            "de executar_comando_admin) e ele responder claramente "
            "permitindo ou negando. Não use espontaneamente e não "
            "use para nenhum outro tipo de confirmação."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "confirmado": types.Schema(
                    type="BOOLEAN",
                    description=(
                        "Verdadeiro se o usuário confirmou o "
                        "comando, falso se negou."
                    ),
                ),
            },
            required=[
                "confirmado",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string, pronta para o Jarvis falar). Se não reconhecer, retorna
# None. Síncrona/bloqueante de propósito (só no caminho automático ou
# de confirmação por voz — nunca mais que alguns segundos além do
# timeout do próprio comando) — quem chama é responsável por rodar
# isso fora do event loop (asyncio.to_thread), igual aos outros
# pacotes.
def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "executar_comando_admin":
        return executar_comando_admin(
            argumentos.get("comando", ""),
            bool(argumentos.get("execucao_longa", False)),
        )

    if nome_funcao == "confirmar_comando_admin":
        return confirmacao.responder_confirmacao_por_voz(
            bool(argumentos.get("confirmado", False))
        )

    return None


def executar_comando_admin(comando, execucao_longa=False):
    comando = (comando or "").strip()

    if not comando:
        return "Nenhum comando informado."

    decisao = politica.avaliar_comando(comando)

    if decisao.automatico:
        timeout = (
            config.TIMEOUT_COMANDO_LONGO_SEGUNDOS
            if execucao_longa
            else config.TIMEOUT_PADRAO_SEGUNDOS
        )

        sucesso, resultado = executor.executar_via_tarefa_agendada(
            comando, timeout
        )

        executor.registrar_log(
            comando, automatico=True, sucesso=sucesso, resumo=resultado
        )

        if sucesso:
            return (
                f"Comando executado automaticamente: '{comando}'. "
                f"{resultado}"
            ).strip()

        return f"Comando '{comando}' falhou: {resultado}"

    confirmacao.solicitar_confirmacao(
        comando,
        decisao.motivo,
        execucao_longa,
        _callback_falar,
    )

    return (
        f"Comando '{comando}' pendente de confirmação: {decisao.motivo} "
        "Pergunte claramente ao usuário se ele confirma executar "
        "exatamente este comando antes de fazer qualquer outra "
        "coisa. Se ele confirmar, chame confirmar_comando_admin com "
        "confirmado=true; se ele negar, chame confirmar_comando_admin "
        "com confirmado=false."
    )
