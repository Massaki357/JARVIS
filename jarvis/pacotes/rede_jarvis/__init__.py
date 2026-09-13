from . import config, mqtt_listener, permissoes, transferencia_arquivos

from google.genai import types


def iniciar_rede_jarvis(callback_falar=None, callback_frame_remoto=None):
    transferencia_arquivos.preparar_ponte_gui()

    mqtt_listener.configurar_callbacks(
        callback_falar,
        callback_frame_remoto,
    )

    mqtt_listener.iniciar_em_thread()


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="enviar_comando_remoto",
        description=(
            "Use esta função somente quando o usuário "
            "pedir explicitamente para executar uma ação "
            "em outro computador do ALFRED (ex: 'peça "
            "para o computador da loja...', 'no "
            "computador de casa...'), ou para enviar um "
            "arquivo local desta máquina para outra. "
            "Nunca use espontaneamente. Se o nome da "
            "máquina ou a ação não estiverem claros, "
            "pergunte ao usuário antes de chamar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "maquina_destino": types.Schema(
                    type="STRING",
                    description=(
                        "Nome da máquina remota, conforme "
                        "o usuário se referiu a ela (ex: "
                        "'casa', 'loja')."
                    ),
                ),
                "comando": types.Schema(
                    type="STRING",
                    enum=[
                        "capturar_tela",
                        "listar_processos",
                        "abrir_app",
                        "buscar_arquivo",
                        "enviar_arquivo",
                        "iniciar_visualizacao_remota",
                        "parar_visualizacao_remota",
                    ],
                    description=(
                        "capturar_tela: tira uma foto da "
                        "tela remota. listar_processos: "
                        "lista os programas abertos na "
                        "máquina remota. abrir_app: abre "
                        "um aplicativo na máquina remota "
                        "(argumentos.nome_app). "
                        "buscar_arquivo: procura um "
                        "arquivo na máquina remota "
                        "(argumentos.termo). "
                        "enviar_arquivo: envia um arquivo "
                        "local desta máquina para a "
                        "máquina destino "
                        "(argumentos.caminho). "
                        "iniciar_visualizacao_remota: "
                        "começa a receber frames "
                        "contínuos da tela remota, "
                        "comentando por voz o que "
                        "aparece. "
                        "parar_visualizacao_remota: "
                        "encerra a visualização remota "
                        "em andamento."
                    ),
                ),
                "argumentos": types.Schema(
                    type="OBJECT",
                    description=(
                        "Argumentos do comando. Use "
                        '{"nome_app": "..."} para '
                        "abrir_app, "
                        '{"termo": "..."} para '
                        "buscar_arquivo, "
                        '{"caminho": "..."} para '
                        "enviar_arquivo. Deixe vazio "
                        "para os demais comandos."
                    ),
                ),
            },
            required=[
                "maquina_destino",
                "comando",
            ],
        ),
    ),
    types.FunctionDeclaration(
        name="responder_permissao_remota",
        description=(
            "Use esta função somente quando o ALFRED "
            "tiver acabado de anunciar por voz um pedido "
            "de permissão remota (comando vindo de outra "
            "máquina aguardando confirmação) e o usuário "
            "responder claramente permitindo ou negando. "
            "Não use espontaneamente e não use para "
            "nenhum outro tipo de confirmação."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "concedido": types.Schema(
                    type="BOOLEAN",
                    description=(
                        "Verdadeiro se o usuário permitiu "
                        "o comando remoto, falso se negou."
                    ),
                ),
            },
            required=[
                "concedido"
            ],
        ),
    ),
    types.FunctionDeclaration(
        name="listar_maquinas_remotas",
        description=(
            "Use esta função somente quando o usuário "
            "pedir explicitamente para saber quais "
            "máquinas do ALFRED estão online agora (ex: "
            "'quais computadores estão online', 'a loja "
            "está online?'). A resposta inclui esta "
            "própria máquina. Não use espontaneamente."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "enviar_comando_remoto":
        return enviar_comando_remoto(
            argumentos.get("maquina_destino", ""),
            argumentos.get("comando", ""),
            argumentos.get("argumentos", {}) or {},
        )

    if nome_funcao == "responder_permissao_remota":
        return responder_permissao_por_voz(
            bool(argumentos.get("concedido", False))
        )

    if nome_funcao == "listar_maquinas_remotas":
        return listar_maquinas_online()

    return None


def enviar_comando_remoto(maquina_destino, comando, argumentos=None):
    if comando == "enviar_arquivo":
        argumentos_com_destino = dict(argumentos or {})
        argumentos_com_destino.setdefault(
            "maquina_destino",
            maquina_destino,
        )

        return transferencia_arquivos.enviar_arquivo(
            config.NOME_MAQUINA,
            argumentos_com_destino,
        )

    return mqtt_listener.enviar_comando(
        maquina_destino,
        comando,
        argumentos,
    )


def responder_permissao_por_voz(concedido):
    return permissoes.responder_permissao_por_voz(concedido)


def listar_maquinas_online():
    return mqtt_listener.listar_maquinas_online()
