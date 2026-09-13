from google.genai import types

from . import cache_canais, cache_contatos, canais, cliente, contatos
from .contatos import _normalizar


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="enviar_dm_discord",
        description=(
            "Envia uma mensagem direta (DM) pelo Discord pra um "
            "amigo específico, pelo nome. Use somente quando o "
            "usuário pedir explicitamente pra mandar mensagem, "
            "chamar ou avisar alguém no Discord por DM (ex: 'manda "
            "mensagem no discord pro Luan chamando ele pra jogar', "
            "'manda um oi pro Pedro no discord'). O amigo é "
            "encontrado automaticamente entre os membros dos "
            "servidores em que o bot está — não peça o ID ou "
            "username exato, só o nome como o usuário falou. Se a "
            "função retornar mais de um candidato parecido, "
            "pergunte ao usuário qual deles antes de chamar de novo "
            "— nunca escolha sozinho. Se não encontrar ninguém, "
            "avise e não tente de novo sozinho. Nunca invente o "
            "conteúdo da mensagem — use exatamente o que o usuário "
            "pediu pra dizer."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome_amigo": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do amigo, exatamente como o usuário "
                        "falou."
                    ),
                ),
                "texto": types.Schema(
                    type="STRING",
                    description="Conteúdo da mensagem a enviar.",
                ),
            },
            required=[
                "nome_amigo",
                "texto",
            ],
        ),
    ),

    types.FunctionDeclaration(
        name="enviar_mensagem_discord",
        description=(
            "Envia uma mensagem num CANAL de texto do Discord — "
            "diferente de enviar_dm_discord, que manda mensagem "
            "direta (DM) pra uma pessoa específica. Use esta função "
            "quando o usuário pedir pra mandar mensagem no Discord "
            "sem ser pra uma pessoa em particular (ex: 'manda "
            "mensagem no discord dizendo que já cheguei', 'avisa no "
            "canal geral que a reunião começou'). Se o usuário "
            "mencionar um nome de pessoa específica, use "
            "enviar_dm_discord em vez desta. Se o usuário não "
            "especificar o canal, deixe o campo canal vazio — a "
            "função decide sozinha se dá pra usar um canal já "
            "conhecido como padrão, ou se precisa perguntar qual "
            "usar. Nunca invente o conteúdo da mensagem."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "canal": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do canal, se o usuário especificou "
                        "(ex: 'geral', 'jogos'). Deixe vazio se ele "
                        "não mencionou nenhum canal."
                    ),
                ),
                "texto": types.Schema(
                    type="STRING",
                    description="Conteúdo da mensagem a enviar.",
                ),
            },
            required=[
                "texto",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "enviar_dm_discord":
        return enviar_dm_discord(
            argumentos.get("nome_amigo", ""),
            argumentos.get("texto", ""),
        )

    if nome_funcao == "enviar_mensagem_discord":
        return enviar_mensagem_discord(
            argumentos.get("canal", ""),
            argumentos.get("texto", ""),
        )

    return None


def iniciar_discord_jarvis():
    cliente.iniciar_conexao()


def enviar_dm_discord(nome_amigo, texto, caminho_anexo=None):
    nome_amigo = (nome_amigo or "").strip()
    texto = (texto or "").strip()

    if not nome_amigo:
        return "Nenhum nome de amigo foi informado."

    if not texto:
        return "Nenhum conteúdo de mensagem foi informado."

    nome_normalizado = _normalizar(nome_amigo)

    contato_do_cache = cache_contatos.obter(nome_normalizado)

    if contato_do_cache:
        sucesso, mensagem = cliente.enviar_dm(
            contato_do_cache["id"],
            texto,
            caminho_anexo,
        )

        if sucesso:
            return mensagem

        print(
            f"[discord_jarvis] Falha ao enviar via cache pra "
            f"'{nome_amigo}' ({mensagem}) — buscando de novo."
        )

    candidato, ambiguos_ou_vazio = contatos.buscar_membro(nome_amigo)

    if candidato is None:
        if ambiguos_ou_vazio:
            nomes = ", ".join(
                contatos.descricao_membro(membro)
                for membro in ambiguos_ou_vazio[:8]
            )

            return (
                f"Encontrei mais de uma pessoa parecida com "
                f"'{nome_amigo}': {nomes}. Qual deles?"
            )

        return (
            f"Não encontrei ninguém chamado '{nome_amigo}' no "
            "servidor."
        )

    sucesso, mensagem = cliente.enviar_dm(
        candidato["id"],
        texto,
        caminho_anexo,
    )

    if sucesso:
        cache_contatos.salvar(
            nome_normalizado,
            {
                "id": candidato["id"],
                "nome_exibicao": candidato["nome_exibicao"],
            },
        )

    return mensagem


def enviar_mensagem_discord(canal_falado, texto, caminho_anexo=None):
    canal_falado = (canal_falado or "").strip()
    texto = (texto or "").strip()

    if not texto:
        return "Nenhum conteúdo de mensagem foi informado."

    if not canal_falado:
        canais_conhecidos = cache_canais.listar_todos()

        if len(canais_conhecidos) == 1:
            canal_unico = next(iter(canais_conhecidos.values()))

            sucesso, mensagem = cliente.enviar_mensagem_canal(
                canal_unico["id"],
                texto,
                caminho_anexo,
            )

            return mensagem

        if not canais_conhecidos:
            return (
                "Ainda não sei em qual canal enviar — diga o nome "
                "do canal."
            )

        opcoes = ", ".join(
            f"#{info['nome']}"
            for info in canais_conhecidos.values()
        )

        return (
            f"Tenho mais de um canal já conhecido ({opcoes}) — em "
            "qual deles devo enviar?"
        )

    nome_normalizado = canais._normalizar(canal_falado)

    canal_do_cache = cache_canais.obter(nome_normalizado)

    if canal_do_cache:
        sucesso, mensagem = cliente.enviar_mensagem_canal(
            canal_do_cache["id"],
            texto,
            caminho_anexo,
        )

        if sucesso:
            return mensagem

        print(
            f"[discord_jarvis] Falha ao enviar via cache pro canal "
            f"'{canal_falado}' ({mensagem}) — buscando de novo."
        )

    candidato, ambiguos_ou_vazio = canais.buscar_canal(canal_falado)

    if candidato is None:
        if ambiguos_ou_vazio:
            nomes = ", ".join(
                canais.descricao_canal(canal)
                for canal in ambiguos_ou_vazio[:8]
            )

            return (
                f"Encontrei mais de um canal parecido com "
                f"'{canal_falado}': {nomes}. Qual deles?"
            )

        return f"Não encontrei nenhum canal chamado '{canal_falado}'."

    sucesso, mensagem = cliente.enviar_mensagem_canal(
        candidato["id"],
        texto,
        caminho_anexo,
    )

    if sucesso:
        cache_canais.salvar(
            nome_normalizado,
            {
                "id": candidato["id"],
                "nome": candidato["nome"],
            },
        )

    return mensagem
