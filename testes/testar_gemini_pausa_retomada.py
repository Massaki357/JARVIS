import asyncio
import os
import sys
import time

from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.cerebro.gemini import cliente_live
from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker

falhas = []
passou = 0


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


def mensagem_handle(handle):
    return SimpleNamespace(
        data=None,
        tool_call=None,
        server_content=None,
        go_away=None,
        session_resumption_update=SimpleNamespace(
            resumable=True,
            new_handle=handle,
        ),
    )


def mensagem_fim_de_turno():
    return SimpleNamespace(
        data=None,
        tool_call=None,
        go_away=None,
        session_resumption_update=None,
        server_content=SimpleNamespace(
            interrupted=None,
            output_transcription=None,
            input_transcription=None,
            turn_complete=True,
        ),
    )


class SessaoFalsa:
    def __init__(self):
        self.fila = asyncio.Queue()

    async def receive(self):
        while True:
            mensagem = await self.fila.get()
            yield mensagem

            conteudo = mensagem.server_content

            if conteudo and conteudo.turn_complete:
                return


def novo_worker():
    trabalhador = GeminiLiveWorker(slug_perfil="completo")
    trabalhador.ativo = True
    trabalhador.alfred_falando = False

    emissoes = []
    trabalhador.solicitou_hibernacao.connect(
        lambda: emissoes.append((time.monotonic(), trabalhador.session_handle))
    )

    return trabalhador, emissoes


async def pausar_como_o_worker(trabalhador):
    trabalhador.hibernacao_solicitada = True
    trabalhador.tarefa_encerramento = asyncio.create_task(
        trabalhador.encerrar_apos_resposta()
    )


async def encerrar(trabalhador, sessao, tarefa):
    trabalhador.ativo = False
    sessao.fila.put_nowait(mensagem_fim_de_turno())
    tarefa.cancel()

    for pendente in (tarefa, trabalhador.tarefa_encerramento):
        if pendente is None:
            continue

        pendente.cancel()

        try:
            await pendente
        except BaseException:
            pass


async def parte1_espera_o_turno_da_despedida():
    titulo("1. A pausa só hiberna depois do turno da despedida registrado")

    trabalhador, emissoes = novo_worker()
    sessao = SessaoFalsa()
    tarefa = asyncio.create_task(
        trabalhador.receber_audio(sessao, asyncio.Queue(), asyncio.Queue())
    )

    inicio = time.monotonic()
    await pausar_como_o_worker(trabalhador)

    await asyncio.sleep(0.2)
    sessao.fila.put_nowait(mensagem_handle("handle_no_meio_do_turno"))

    await asyncio.sleep(3.3)

    checar(
        emissoes == [],
        "aos 3,5 s, com a despedida ainda sendo gerada, NÃO hibernou "
        f"(emissões: {[(round(t - inicio, 1), h) for t, h in emissoes]})",
    )

    sessao.fila.put_nowait(mensagem_fim_de_turno())
    await asyncio.sleep(0.3)
    sessao.fila.put_nowait(mensagem_handle("handle_com_despedida"))

    await asyncio.sleep(1.2)

    checar(len(emissoes) == 1, f"hibernou exatamente uma vez ({len(emissoes)})")

    if emissoes:
        checar(
            emissoes[0][1] == "handle_com_despedida",
            "o handle guardado na hibernação já inclui a despedida "
            f"({emissoes[0][1]})",
        )

    await encerrar(trabalhador, sessao, tarefa)


async def parte2_teto_de_seguranca():
    titulo("2. Sem fim de turno, hiberna mesmo assim ao atingir o teto")

    teto_original = cliente_live.LIMITE_ESPERA_PAUSA_SEGUNDOS
    cliente_live.LIMITE_ESPERA_PAUSA_SEGUNDOS = 1.0

    try:
        trabalhador, emissoes = novo_worker()
        sessao = SessaoFalsa()
        tarefa = asyncio.create_task(
            trabalhador.receber_audio(sessao, asyncio.Queue(), asyncio.Queue())
        )

        await pausar_como_o_worker(trabalhador)
        await asyncio.sleep(1.8)

        checar(
            len(emissoes) == 1,
            f"com o teto em 1 s e nenhum fim de turno, hibernou ({len(emissoes)})",
        )

        await encerrar(trabalhador, sessao, tarefa)

    finally:
        cliente_live.LIMITE_ESPERA_PAUSA_SEGUNDOS = teto_original


async def parte3_encerrar_nao_muda():
    titulo("3. encerrar_chamada continua com a espera fixa de sempre")

    trabalhador, _ = novo_worker()
    encerramentos = []
    trabalhador.solicitou_encerramento.connect(
        lambda: encerramentos.append(time.monotonic())
    )

    inicio = time.monotonic()
    trabalhador.hibernacao_solicitada = False
    trabalhador.tarefa_encerramento = asyncio.create_task(
        trabalhador.encerrar_apos_resposta()
    )

    await asyncio.sleep(3.3)

    checar(
        len(encerramentos) == 1 and 2.5 < encerramentos[0] - inicio < 3.2,
        "encerrar sai em ~2,8 s, sem esperar turno nem handle "
        f"({[round(t - inicio, 1) for t in encerramentos]})",
    )


async def principal():
    await parte1_espera_o_turno_da_despedida()
    await parte2_teto_de_seguranca()
    await parte3_encerrar_nao_muda()


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
