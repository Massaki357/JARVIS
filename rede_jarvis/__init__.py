from . import config, mqtt_listener, permissoes, transferencia_arquivos

# Usado só para montar as FunctionDeclaration deste pacote — ver
# obter_function_declarations() logo abaixo. Isolar essa dependência
# aqui (em vez de em cada submódulo) mantém o resto do pacote livre
# de qualquer referência ao SDK do Gemini.
from google.genai import types


# Ponto de entrada único do pacote. Sobe o listener do MQTT em
# background (idempotente — chamadas repetidas não conectam uma
# segunda vez) e (re)registra os callbacks usados para o Jarvis
# "falar" algo por voz e para injetar frames de visualização remota
# na sessão Live local.
#
# Deve ser chamada a partir da thread principal (GUI) — prepara
# também a ponte usada pelo diálogo de "salvar arquivo recebido"
# (ver transferencia_arquivos.preparar_ponte_gui). Isso é wiring
# específico deste pacote (sessão Gemini/callbacks) que não faz parte
# do contrato genérico obter_function_declarations()/despachar() — ver
# INTEGRATION.md na raiz do projeto para o passo a passo completo de
# como religar este pacote a um novo arquivo cliente.
def iniciar_rede_jarvis(callback_falar=None, callback_frame_remoto=None):
    transferencia_arquivos.preparar_ponte_gui()

    mqtt_listener.configurar_callbacks(
        callback_falar,
        callback_frame_remoto,
    )

    mqtt_listener.iniciar_em_thread()


# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar(). O cliente
# Gemini Live só precisa conhecer essas duas funções — nunca os
# nomes de tool individuais deste pacote.
# ============================================================

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


# Retorna a lista de FunctionDeclaration deste pacote. O cliente
# Gemini Live só faz tools.extend(rede_jarvis.obter_function_declarations())
# — nunca precisa listar os nomes das tools individualmente.
def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string, pronta para o Jarvis falar). Se não reconhecer, retorna
# None — o chamador deve tentar outro pacote ou tratar como não
# encontrado. Síncrona/bloqueante de propósito: quem chama (o cliente
# Gemini Live) é responsável por rodar isso fora do event loop (ex:
# asyncio.to_thread), igual já fazia antes desta função existir.
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


# "enviar_arquivo" é tratado localmente: é a própria máquina que
# envia um arquivo que ela tem, não um comando para a máquina remota
# executar. Todos os outros comandos são de fato despachados pelo
# MQTT para maquina_destino executar e responder.
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


# Local e imediato — não faz nenhuma chamada de rede (ver
# mqtt_listener.listar_maquinas_online).
def listar_maquinas_online():
    return mqtt_listener.listar_maquinas_online()
