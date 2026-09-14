import asyncio
import base64
import json
import os
import sys
import tempfile

from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from google.genai import types
from google.genai.live import AsyncSession

from jarvis.cerebro.gemini import gerador_avisos
from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker, _partes_imagem_resposta
from jarvis.cerebro.openai_realtime.cliente_realtime import OpenAIRealtimeWorker
from jarvis.pacotes.criar_arquivo import config as config_criar
from jarvis.pacotes.criar_arquivo import escritor
from jarvis.servicos import aviso_ferramenta

falhas = []
passou = 0

JPEG = b"\xff\xd8\xff\xe0imagem-falsa\xff\xd9"


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


def parte1_criar_arquivo_entende_pasta_em_portugues():
    titulo("1. criar_arquivo aceita a pasta falada em português")

    base = Path(tempfile.mkdtemp())
    pastas = [base / "Desktop", base / "Documents", base / "Downloads"]

    for pasta in pastas:
        pasta.mkdir()

    original = config_criar.pastas_permitidas
    config_criar.pastas_permitidas = lambda: list(pastas)

    try:
        for falada, esperada in (
            ("área de trabalho", "Desktop"),
            ("Área de Trabalho", "Desktop"),
            ("minha área de trabalho", "Desktop"),
            ("documentos", "Documents"),
            ("Downloads", "Downloads"),
        ):
            sucesso, mensagem = escritor.criar_arquivo("lista", "conteudo", falada)

            checar(
                sucesso and esperada in mensagem,
                f"'{falada}' cria em {esperada} ({mensagem[:70]})",
            )

        for falada in ("C:\\Windows", "../..", "pasta secreta", "de"):
            sucesso, mensagem = escritor.criar_arquivo("lista", "conteudo", falada)

            checar(
                not sucesso and mensagem.startswith("NÃO criei o arquivo"),
                f"'{falada}' é recusada e a recusa começa com 'NÃO criei'",
            )

        criados = sorted(p.parent.name for p in base.rglob("*.txt"))

        checar(
            all(nome in ("Desktop", "Documents", "Downloads") for nome in criados),
            f"nenhum arquivo saiu das pastas permitidas ({criados})",
        )

    finally:
        config_criar.pastas_permitidas = original


def parte2_audios_de_aviso():
    titulo("2. Áudios de aviso: um por ferramenta, na voz configurada")

    nomes = gerador_avisos.nomes_para_gerar()
    pasta = aviso_ferramenta.pasta_audios()
    faltando = [nome for nome in nomes if not (pasta / f"{nome}.wav").is_file()]

    checar(not faltando, f"todos os {len(nomes)} áudios existem em {pasta} (faltando: {faltando})")

    pcm = aviso_ferramenta.pcm_do_aviso("criar_arquivo")

    checar(
        bool(pcm) and len(pcm) / 2 / aviso_ferramenta.TAXA_AMOSTRAGEM > 1.0,
        "o áudio de criar_arquivo carrega como PCM de 24 kHz com mais de 1 s",
    )

    checar(
        aviso_ferramenta.pcm_do_aviso("ferramenta_que_nao_existe")
        == aviso_ferramenta.pcm_do_aviso(aviso_ferramenta.NOME_GENERICO),
        "ferramenta sem áudio próprio cai no aviso genérico",
    )

    checar(
        aviso_ferramenta.ferramenta_do_aviso([("executar_ferramenta", {"nome": "criar_arquivo"})])
        == "criar_arquivo",
        "por executar_ferramenta, o aviso usa o nome da ferramenta real",
    )

    checar(
        aviso_ferramenta.ferramenta_do_aviso([("pausar_chamada", {})]) is None
        and aviso_ferramenta.ferramenta_do_aviso([("rolar_pagina", {})], ("rolar_pagina",)) is None,
        "pausar/encerrar e as ferramentas silenciosas não avisam",
    )


class WebsocketFalso:
    def __init__(self):
        self.enviados = []

    async def send(self, texto):
        self.enviados.append(json.loads(texto))


def novo_gemini():
    websocket = WebsocketFalso()
    sessao = AsyncSession(api_client=SimpleNamespace(vertexai=False), websocket=websocket)

    trabalhador = GeminiLiveWorker(slug_perfil="completo")
    trabalhador.ativo = True
    trabalhador.sessao = sessao
    trabalhador.fila_saida_atual = asyncio.Queue()

    return trabalhador, sessao, websocket


def chamada(nome, identificador, argumentos=None):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(name=nome, args=argumentos or {}, id=identificador)]
    )


def resposta(identificador, nome, texto, partes=None):
    return types.FunctionResponse(
        id=identificador, name=nome, response={"result": texto}, parts=partes
    )


def falso_processamento(trabalhador, segundos, respostas):
    async def processar(tool_call):
        await asyncio.sleep(segundos)
        return respostas, False

    trabalhador.processar_chamada_de_funcao = processar


def audio_na_fila(fila):
    blocos = []

    while not fila.empty():
        blocos.append(fila.get_nowait())

    return b"".join(blocos)


async def parte3_gemini_aviso_so_quando_demora():
    titulo("3. Gemini: aviso falado só quando a ferramenta passa de 1,5 s")

    trabalhador, sessao, _ = novo_gemini()
    falso_processamento(trabalhador, 2.2, [resposta("id-lento", "executar_ferramenta", "ok")])

    await trabalhador._executar_chamada_de_funcao_com_timeout(
        sessao, chamada("executar_ferramenta", "id-lento", {"nome": "criar_arquivo"})
    )

    checar(
        audio_na_fila(trabalhador.fila_saida_atual) == aviso_ferramenta.pcm_do_aviso("criar_arquivo"),
        "ferramenta de 2,2 s: tocou o aviso de criar_arquivo inteiro",
    )

    trabalhador, sessao, _ = novo_gemini()
    falso_processamento(trabalhador, 0.3, [resposta("id-rapido", "executar_ferramenta", "ok")])

    await trabalhador._executar_chamada_de_funcao_com_timeout(
        sessao, chamada("executar_ferramenta", "id-rapido", {"nome": "criar_arquivo"})
    )
    await asyncio.sleep(1.6)

    checar(
        trabalhador.fila_saida_atual.empty(),
        "ferramenta de 0,3 s: nenhum aviso",
    )


def mensagens(websocket, tipo):
    return [m[tipo] for m in websocket.enviados if tipo in m]


async def parte4_gemini_cancelamento_nao_perde_resultado():
    titulo("4. Gemini: chamada cancelada pelo servidor não perde o resultado")

    trabalhador, sessao, websocket = novo_gemini()
    texto = "NÃO criei o arquivo: 'xyz' não é uma pasta permitida."
    falso_processamento(trabalhador, 0.8, [resposta("id-cancelado", "executar_ferramenta", texto)])

    execucao = asyncio.create_task(
        trabalhador._executar_chamada_de_funcao_com_timeout(
            sessao, chamada("executar_ferramenta", "id-cancelado", {"nome": "criar_arquivo"})
        )
    )
    await asyncio.sleep(0.2)
    trabalhador._registrar_cancelamento(["id-cancelado"])
    await execucao

    checar(
        not mensagens(websocket, "tool_response"),
        "não mandou tool_response para o id cancelado (o servidor descartaria)",
    )

    turnos = mensagens(websocket, "client_content")
    textos = json.dumps(turnos, ensure_ascii=False)

    checar(
        len(turnos) == 1 and "JÁ FOI EXECUTADA" in textos and texto in textos,
        "entregou o resultado real num turno, avisando que a ação já rodou",
    )

    trabalhador, sessao, websocket = novo_gemini()
    falso_processamento(trabalhador, 0.1, [resposta("id-corrida", "criar_arquivo", "Arquivo criado.")])

    await trabalhador._executar_chamada_de_funcao_com_timeout(
        sessao, chamada("criar_arquivo", "id-corrida")
    )
    trabalhador._registrar_cancelamento(["id-corrida"])
    await asyncio.gather(*list(trabalhador.tarefas_funcao_ativas))

    checar(
        len(mensagens(websocket, "tool_response")) == 1
        and "Arquivo criado." in json.dumps(mensagens(websocket, "client_content"), ensure_ascii=False),
        "cancelamento que chega depois da resposta: reentrega o resultado",
    )

    trabalhador, sessao, websocket = novo_gemini()
    falso_processamento(
        trabalhador,
        0.6,
        [resposta("id-imagem", "analisar_tela", "Analise a imagem.", _partes_imagem_resposta(JPEG))],
    )

    execucao = asyncio.create_task(
        trabalhador._executar_chamada_de_funcao_com_timeout(sessao, chamada("analisar_tela", "id-imagem"))
    )
    await asyncio.sleep(0.2)
    trabalhador._registrar_cancelamento(["id-imagem"])
    await execucao

    partes = [
        parte
        for turno in mensagens(websocket, "client_content")
        for conteudo in turno.get("turns", [])
        for parte in conteudo.get("parts", [])
    ]
    dados = [
        (parte.get("inlineData") or parte.get("inline_data") or {}).get("data")
        for parte in partes
    ]

    checar(
        any(d and base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)) == JPEG for d in dados),
        "análise de tela cancelada: a imagem vai junto no turno de entrega",
    )


def mensagem_fim_de_turno():
    return SimpleNamespace(
        data=None,
        tool_call=None,
        tool_call_cancellation=None,
        go_away=None,
        session_resumption_update=None,
        server_content=SimpleNamespace(
            interrupted=None,
            output_transcription=None,
            input_transcription=None,
            turn_complete=True,
        ),
    )


class SessaoRecebimento:
    def __init__(self, mensagens):
        self._mensagens = list(mensagens)

    async def receive(self):
        await asyncio.sleep(0.01)

        while self._mensagens:
            yield self._mensagens.pop(0)


async def parte5_status_volta_para_ouvindo():
    titulo("5. Status volta para 'está ouvindo' depois da ferramenta")

    for com_tarefa, esperado in ((False, True), (True, False)):
        trabalhador, _, _ = novo_gemini()
        status = []
        trabalhador.status_recebido.connect(status.append)
        trabalhador.voltar_status_ouvindo = True

        if com_tarefa:
            trabalhador.tarefas_funcao_ativas.append(object())

        sessao = SessaoRecebimento([mensagem_fim_de_turno()])
        trabalhador.ativo = True

        async def desligar():
            await asyncio.sleep(0.3)
            trabalhador.ativo = False

        await asyncio.gather(
            trabalhador.receber_audio(sessao, asyncio.Queue(), asyncio.Queue()),
            desligar(),
        )

        ouvindo = any("está ouvindo" in s for s in status)

        checar(
            ouvindo == esperado,
            "Gemini: fim de turno "
            + ("com ferramenta ainda rodando NÃO muda o status" if com_tarefa else "depois da ferramenta mostra 'está ouvindo'"),
        )

    trabalhador = OpenAIRealtimeWorker(slug_perfil="completo")
    trabalhador.lock_envio = asyncio.Lock()
    trabalhador.ativo = True
    status = []
    trabalhador.status_recebido.connect(status.append)
    trabalhador.voltar_status_ouvindo = True

    class Conexao:
        def __aiter__(self):
            async def gerar():
                yield SimpleNamespace(type="response.done")

            return gerar()

    await trabalhador.receber_eventos(Conexao(), asyncio.Queue(), asyncio.Queue())

    checar(
        any("está ouvindo" in s for s in status),
        "OpenAI: response.done depois da ferramenta mostra 'está ouvindo'",
    )


class ConexaoOpenAI:
    def __init__(self):
        self.itens = []
        conexao = self

        class _Item:
            async def create(self, item):
                conexao.itens.append(item)

        class _Resposta:
            async def create(self):
                return None

        self.conversation = SimpleNamespace(item=_Item())
        self.response = _Resposta()


async def parte6_openai_aviso_so_quando_demora():
    titulo("6. OpenAI: aviso falado só quando a ferramenta passa de 1,5 s")

    for segundos, deve_avisar in ((2.2, True), (0.3, False)):
        trabalhador = OpenAIRealtimeWorker(slug_perfil="completo")
        trabalhador.lock_envio = asyncio.Lock()
        trabalhador.ativo = True
        trabalhador.fila_saida_atual = asyncio.Queue()

        async def despachar(nome, args, segundos=segundos):
            await asyncio.sleep(segundos)
            return "Arquivo criado."

        trabalhador._despachar_para_pacotes = despachar
        conexao = ConexaoOpenAI()

        await trabalhador.processar_chamada_de_funcao(
            conexao, "call-1", "executar_ferramenta", {"nome": "criar_arquivo"}, asyncio.Queue()
        )
        await asyncio.sleep(1.6 if not deve_avisar else 0.1)

        itens = []

        while not trabalhador.fila_saida_atual.empty():
            itens.append(trabalhador.fila_saida_atual.get_nowait())

        audio = b"".join(bloco for _, bloco in itens)

        if deve_avisar:
            checar(
                audio == aviso_ferramenta.pcm_do_aviso("criar_arquivo")
                and all(item_id is None for item_id, _ in itens),
                "ferramenta de 2,2 s: tocou o aviso (sem item_id, fora da fala do modelo)",
            )
        else:
            checar(not itens, "ferramenta de 0,3 s: nenhum aviso")

        checar(
            any(item.get("output") == "Arquivo criado." for item in conexao.itens),
            f"o resultado continua indo por function_call_output ({segundos}s)",
        )


async def principal():
    parte1_criar_arquivo_entende_pasta_em_portugues()
    parte2_audios_de_aviso()
    await parte3_gemini_aviso_so_quando_demora()
    await parte4_gemini_cancelamento_nao_perde_resultado()
    await parte5_status_volta_para_ouvindo()
    await parte6_openai_aviso_so_quando_demora()


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
