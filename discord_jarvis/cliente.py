# Conexão persistente com o bot do Discord. discord.py precisa de um
# loop asyncio vivo o tempo todo (não é compatível com rodar só
# durante um despachar() pontual, como as chamadas HTTP de outros
# pacotes) — por isso roda numa thread própria, com seu próprio
# loop, mesmo padrão já usado em rede_jarvis/mqtt_listener.py
# (thread de fundo) e visualizacao_remota.py (loop dedicado +
# run_coroutine_threadsafe como ponte pra chamadas síncronas).
import asyncio
import threading

import discord

from . import config

_cliente = None
_loop = None
_pronto = threading.Event()
_thread_iniciada = False
_lock_inicio = threading.Lock()


def _montar_intents():
    intents = discord.Intents.default()

    # Necessário pra listar/buscar membros do servidor por nome
    # (Guild.fetch_members) — ver aviso completo em config.py.
    intents.members = True

    # Parte do setup padrão do bot documentado em config.py — não
    # usado ainda por nenhuma tool específica, mas precisa estar
    # ativo pro bot funcionar como esperado no Developer Portal.
    intents.message_content = True

    return intents


def _rodar_loop_do_bot():
    global _loop, _cliente

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    _cliente = discord.Client(intents=_montar_intents())

    @_cliente.event
    async def on_ready():
        print(f"[discord_jarvis] Conectado como {_cliente.user}.")
        _pronto.set()

    try:
        _loop.run_until_complete(
            _cliente.start(config.DISCORD_BOT_TOKEN)
        )

    except Exception as erro:
        print(f"[discord_jarvis] Conexão com o Discord encerrada: {erro}")

    finally:
        _pronto.clear()


# Sobe a conexão com o bot em background, se ainda não estiver de
# pé — idempotente, mesmo padrão de rede_jarvis.iniciar_rede_jarvis:
# GeminiLiveWorker é recriado a cada chamada de voz, mas a conexão
# com o Discord deve persistir independente disso, então só a
# primeira chamada de fato inicia a thread.
def iniciar_conexao():
    global _thread_iniciada

    with _lock_inicio:
        if _thread_iniciada:
            return

        if not config.DISCORD_BOT_TOKEN:
            print(
                "[discord_jarvis] DISCORD_BOT_TOKEN não configurado "
                "no .env — conexão com o Discord não foi iniciada."
            )
            return

        threading.Thread(
            target=_rodar_loop_do_bot,
            daemon=True,
        ).start()

        _thread_iniciada = True


# Roda uma corrotina no loop do bot a partir de qualquer thread
# (despachar() roda numa thread de fundo, via asyncio.to_thread) e
# espera o resultado — mesma técnica de run_coroutine_threadsafe já
# usada em rede_jarvis/visualizacao_remota.py. Espera a conexão
# ficar pronta antes de agendar, se ainda não estiver.
def _rodar_no_loop_do_bot(corrotina, timeout):
    if not _pronto.wait(timeout=config.TIMEOUT_CONEXAO_SEGUNDOS):
        raise RuntimeError(
            "O bot do Discord ainda não conectou (ou a conexão "
            "falhou) — confirme DISCORD_BOT_TOKEN no .env."
        )

    future = asyncio.run_coroutine_threadsafe(
        corrotina,
        _loop,
    )

    return future.result(timeout=timeout)


# Retorna uma lista de dicts {"id", "nome_exibicao", "username",
# "apelido"} de todos os membros de todos os servidores em que o bot
# está, sem duplicar quem estiver em mais de um servidor em comum.
# Nunca lança exceção — retorna lista vazia se algo falhar.
def listar_membros():
    async def _coletar():
        vistos = set()
        resultado = []

        for guild in _cliente.guilds:
            async for membro in guild.fetch_members(limit=None):
                if membro.id in vistos:
                    continue

                vistos.add(membro.id)

                resultado.append(
                    {
                        "id": membro.id,
                        "nome_exibicao": membro.display_name,
                        "username": membro.name,
                        "apelido": membro.nick,
                    }
                )

        return resultado

    try:
        return _rodar_no_loop_do_bot(
            _coletar(),
            timeout=config.TIMEOUT_LISTAGEM_MEMBROS_SEGUNDOS,
        )

    except Exception as erro:
        print(f"[discord_jarvis] Falha ao listar membros: {erro}")
        return []


# Envia uma DM pro usuário de ID user_id. Nunca lança exceção —
# sempre retorna (sucesso: bool, mensagem: str).
def enviar_dm(user_id, texto, caminho_anexo=None):
    async def _enviar():
        usuario = _cliente.get_user(
            user_id
        ) or await _cliente.fetch_user(user_id)

        if caminho_anexo:
            await usuario.send(
                texto,
                file=discord.File(caminho_anexo),
            )

        else:
            await usuario.send(texto)

        return usuario

    try:
        usuario = _rodar_no_loop_do_bot(
            _enviar(),
            timeout=config.TIMEOUT_OPERACAO_SEGUNDOS,
        )

    except discord.Forbidden:
        return False, (
            "Não consegui enviar a mensagem — essa pessoa tem DMs "
            "bloqueadas para quem não é amigo, ou bloqueou o bot."
        )

    except discord.NotFound:
        return False, "Usuário não encontrado no Discord."

    except discord.HTTPException as erro:
        return False, f"Falha ao enviar a mensagem no Discord: {erro}"

    except (RuntimeError, TimeoutError) as erro:
        return False, f"Falha na conexão com o Discord: {erro}"

    return True, f"Mensagem enviada para {usuario} no Discord."


# Retorna uma lista de dicts {"id", "nome", "servidor"} de todos os
# canais de TEXTO de todos os servidores em que o bot está. Nunca
# lança exceção — retorna lista vazia se algo falhar.
def listar_canais():
    async def _coletar():
        resultado = []

        for guild in _cliente.guilds:
            for canal in guild.text_channels:
                resultado.append(
                    {
                        "id": canal.id,
                        "nome": canal.name,
                        "servidor": guild.name,
                    }
                )

        return resultado

    try:
        return _rodar_no_loop_do_bot(
            _coletar(),
            timeout=config.TIMEOUT_LISTAGEM_MEMBROS_SEGUNDOS,
        )

    except Exception as erro:
        print(f"[discord_jarvis] Falha ao listar canais: {erro}")
        return []


# Envia uma mensagem no canal de ID channel_id. Nunca lança exceção
# — sempre retorna (sucesso: bool, mensagem: str).
def enviar_mensagem_canal(channel_id, texto, caminho_anexo=None):
    async def _enviar():
        canal = _cliente.get_channel(
            channel_id
        ) or await _cliente.fetch_channel(channel_id)

        if caminho_anexo:
            await canal.send(
                texto,
                file=discord.File(caminho_anexo),
            )

        else:
            await canal.send(texto)

        return canal

    try:
        canal = _rodar_no_loop_do_bot(
            _enviar(),
            timeout=config.TIMEOUT_OPERACAO_SEGUNDOS,
        )

    except discord.Forbidden:
        return False, (
            "Não consegui enviar a mensagem — o bot não tem "
            "permissão de escrever nesse canal."
        )

    except discord.NotFound:
        return False, "Canal não encontrado no Discord."

    except discord.HTTPException as erro:
        return False, f"Falha ao enviar a mensagem no Discord: {erro}"

    except (RuntimeError, TimeoutError) as erro:
        return False, f"Falha na conexão com o Discord: {erro}"

    return True, f"Mensagem enviada no canal #{canal.name}."
