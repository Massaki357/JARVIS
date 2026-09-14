import asyncio
import base64
import json
import os
import sys

from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from google.genai import types
from google.genai.live import AsyncSession

from jarvis.cerebro.gemini import cliente_live
from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker
from jarvis.nucleo import perfis

falhas = []
passou = 0

JPEG_TELA = b"\xff\xd8\xff\xe0tela-falsa\xff\xd9"
JPEG_CAMERA = b"\xff\xd8\xff\xe0camera-falsa\xff\xd9"


def checar(condicao, descricao):
    global passou

    if condicao:
        passou += 1
        print(f"  OK    {descricao}")
    else:
        falhas.append(descricao)
        print(f"  FALHA {descricao}")


def titulo(texto):
    print(f"\n=== {texto} ===")


class WebsocketFalso:
    def __init__(self):
        self.enviados = []

    async def send(self, texto):
        self.enviados.append(json.loads(texto))


def sessao_real_do_sdk():
    websocket = WebsocketFalso()
    sessao = AsyncSession(
        api_client=SimpleNamespace(vertexai=False),
        websocket=websocket,
    )
    return sessao, websocket


def novo_worker(sessao):
    trabalhador = GeminiLiveWorker(slug_perfil="completo")
    trabalhador.ativo = True
    trabalhador.sessao = sessao
    return trabalhador


def chamada(nome, identificador):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(name=nome, args={}, id=identificador)]
    )


async def pedir_por_voz(nome, jpeg_esperado, origem):
    sessao, websocket = sessao_real_do_sdk()
    trabalhador = novo_worker(sessao)

    respostas, _ = await trabalhador.processar_chamada_de_funcao(
        chamada(nome, f"id-{nome}")
    )

    try:
        await sessao.send_tool_response(function_responses=respostas)
        serializou = True
    except TypeError as erro:
        serializou = False
        checar(False, f"{nome}: o SDK serializa a resposta com imagem ({erro})")

    turnos_de_usuario = [m for m in websocket.enviados if "client_content" in m]

    checar(
        not turnos_de_usuario,
        f"{nome}: a imagem NÃO vai como turno de usuário separado "
        f"({len(turnos_de_usuario)} turno(s))",
    )

    if not serializou:
        return

    resposta = websocket.enviados[-1]["tool_response"]["functionResponses"][0]
    partes = resposta.get("parts") or []
    dados = [
        (parte.get("inline_data") or parte.get("inlineData") or {}).get("data")
        for parte in partes
    ]

    checar(
        len(dados) == 1 and dados[0] and base64.b64decode(dados[0]) == jpeg_esperado,
        f"{nome}: a imagem capturada vai DENTRO da resposta da função",
    )
    checar(
        resposta.get("id") == f"id-{nome}",
        f"{nome}: a resposta responde o id da chamada",
    )
    checar(
        f"da {origem}" in str(resposta.get("response", {}).get("result", "")),
        f"{nome}: o texto da resposta é a instrução de análise da {origem}",
    )


async def parte1_voz_leva_a_imagem_na_resposta():
    titulo("1. Pedido por voz: a imagem vai dentro da resposta da função")

    await pedir_por_voz("analisar_tela", JPEG_TELA, "tela")
    await pedir_por_voz("analisar_camera", JPEG_CAMERA, "câmera")


async def parte2_botao_continua_como_turno():
    titulo("2. Botão (sem chamada aberta) continua mandando o turno com a imagem")

    sessao, websocket = sessao_real_do_sdk()
    trabalhador = novo_worker(sessao)

    retorno = await trabalhador.processar_funcao_visual(
        "analisar_tela",
        origem="botão",
    )

    turnos = [m for m in websocket.enviados if "client_content" in m]

    checar(len(turnos) == 1, f"mandou um turno de usuário ({len(turnos)})")
    checar(
        isinstance(retorno, tuple) and retorno[1] is None,
        "o botão não devolve imagem para resposta de função",
    )


def parte3_porte_da_visao_nao_compete_com_a_nativa():
    titulo("3. descrever_* some quando a visão nativa está declarada")

    def nomes(lista):
        declaracoes = [types.FunctionDeclaration(name=n) for n in lista]
        return [d.name for d in perfis.filtrar_declaracoes(declaracoes, None)]

    com_nativa = nomes(
        ["analisar_tela", "analisar_camera", "descrever_tela", "descrever_camera", "identificar_planta"]
    )
    checar(
        "descrever_tela" not in com_nativa and "descrever_camera" not in com_nativa,
        f"com analisar_tela/analisar_camera, os portes saem ({com_nativa})",
    )
    checar(
        "identificar_planta" in com_nativa,
        "as outras ferramentas de visão ficam",
    )

    so_tela = nomes(["analisar_tela", "descrever_tela", "descrever_camera"])
    checar(
        so_tela == ["analisar_tela", "descrever_camera"],
        f"sai só o porte cuja nativa existe ({so_tela})",
    )

    modo_local = nomes(["descrever_tela", "descrever_camera"])
    checar(
        modo_local == ["descrever_tela", "descrever_camera"],
        f"sem visão nativa (modo local), os portes ficam ({modo_local})",
    )


async def principal():
    cliente_live.capturar_monitor_do_cursor_bytes = lambda: JPEG_TELA
    cliente_live.capturar_camera_bytes = lambda: JPEG_CAMERA

    await parte1_voz_leva_a_imagem_na_resposta()
    await parte2_botao_continua_como_turno()
    parte3_porte_da_visao_nao_compete_com_a_nativa()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])

    asyncio.run(principal())

    print("\n" + "=" * 60)

    if falhas:
        print(f"{passou} verificacoes passaram, {len(falhas)} FALHARAM:")

        for f in falhas:
            print(f"  - {f}")

        sys.exit(1)

    print(f"{passou} verificacoes passaram. Nenhuma falha.")
