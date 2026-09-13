import asyncio
import base64
import os
import sys

from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.cerebro.openai_realtime.cliente_realtime import (
    CANAIS,
    TAXA_SAIDA,
    OpenAIRealtimeWorker,
)

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


class ConexaoFalsa:
    def __init__(self, eventos=None):
        self.truncates = []
        self._eventos = list(eventos or [])

        conexao = self

        class _Item:
            async def truncate(self, **kwargs):
                conexao.truncates.append(kwargs)

        self.conversation = SimpleNamespace(item=_Item())

    def __aiter__(self):
        return self._iterar()

    async def _iterar(self):
        for evento in self._eventos:
            yield evento


def delta(item_id, n_bytes=1024):
    return SimpleNamespace(
        type="response.output_audio.delta",
        item_id=item_id,
        delta=base64.b64encode(b"\x01\x00" * (n_bytes // 2)).decode(),
    )


def fala_do_usuario():
    return SimpleNamespace(
        type="input_audio_buffer.speech_started",
        item_id="msg_usuario",
        audio_start_ms=1000,
    )


def novo_worker(interrupcao):
    trabalhador = OpenAIRealtimeWorker(slug_perfil="completo")
    trabalhador.lock_envio = asyncio.Lock()
    trabalhador.ativo = True

    trabalhador.interrupcao_habilitada = interrupcao

    niveis = []
    trabalhador.nivel_audio.connect(niveis.append)

    return trabalhador, niveis


def bytes_de_ms(ms):
    return int(ms * TAXA_SAIDA * 2 * CANAIS / 1000)


def parte1_configuracao():
    titulo("1. turn_detection da sessão")

    ligado, _ = novo_worker(True)
    desligado, _ = novo_worker(False)

    checar(
        ligado._configuracao_vad()
        == {"type": "server_vad", "interrupt_response": True},
        "com interrupção, interrupt_response vai explícito em True",
    )

    checar(
        desligado._configuracao_vad() == {"type": "server_vad"},
        "sem interrupção, o dicionário é idêntico ao de antes da mudança",
    )


def parte2_microfone():
    titulo("2. Quando o microfone é descartado")

    for interrupcao in (False, True):
        w, _ = novo_worker(interrupcao)

        modo = "com" if interrupcao else "sem"

        w.alfred_falando = False
        w.processando_ferramenta = False
        checar(
            not w._microfone_bloqueado(),
            f"{modo} interrupção: calado e sem ferramenta, o microfone passa",
        )

        w.alfred_falando = True
        checar(
            w._microfone_bloqueado() is (not interrupcao),
            f"{modo} interrupção: com o ALFRED falando, o microfone "
            f"{'PASSA' if interrupcao else 'é bloqueado'}",
        )

        w.alfred_falando = False
        w.processando_ferramenta = True
        checar(
            w._microfone_bloqueado(),
            f"{modo} interrupção: executando ferramenta, sempre bloqueia",
        )


async def parte3_corte():
    titulo("3. _interromper_fala")

    w, niveis = novo_worker(True)
    conexao = ConexaoFalsa()
    fila_saida = asyncio.Queue()

    w.item_audio_tocando = "item_A"
    w.bytes_tocados_item = bytes_de_ms(1500)
    w.alfred_falando = True

    for item in ("item_A", "item_A", "item_A", "item_B"):
        fila_saida.put_nowait((item, b"\x00\x00" * 512))

    await w._interromper_fala(conexao, fila_saida)

    checar(fila_saida.empty(), "a fila de saída é esvaziada na hora")
    checar(not w.alfred_falando, "o microfone é solto sem esperar o atraso")
    checar(niveis and niveis[-1] == 0.0, "as barras voltam a zero")
    checar(w.interrupcoes_na_chamada == 1, "a interrupção é contada")

    checar(
        {"item_A", "item_B"} <= w.itens_interrompidos,
        "o item tocando E os que estavam na fila são marcados como cortados",
    )

    checar(
        conexao.truncates
        == [{"item_id": "item_A", "content_index": 0, "audio_end_ms": 1500}],
        f"o servidor ouve até onde a fala foi escutada ({conexao.truncates})",
    )

    w2, _ = novo_worker(True)
    conexao2 = ConexaoFalsa()
    w2.item_audio_tocando = "item_C"
    w2.bytes_tocados_item = 0
    w2.alfred_falando = True

    await w2._interromper_fala(conexao2, asyncio.Queue())

    checar(
        conexao2.truncates == [],
        "com 0 ms ouvidos, não manda truncate (evita erro do servidor)",
    )

    w3, _ = novo_worker(True)
    w3.bytes_tocados_item = bytes_de_ms(1000) + 47
    checar(
        w3._milissegundos_tocados() == 1000,
        "ms arredondados para baixo — nunca acima da duração real",
    )


async def parte4_eventos():
    titulo("4. receber_eventos: fala, corte e descarte do resto")

    w, _ = novo_worker(True)
    fila_saida = asyncio.Queue()
    fila_microfone = asyncio.Queue()

    fila_microfone.put_nowait(b"voz do usuario")

    w.item_audio_tocando = "item_A"
    w.bytes_tocados_item = bytes_de_ms(800)

    conexao = ConexaoFalsa(
        [
            delta("item_A"),
            fala_do_usuario(),
            delta("item_A"),
            delta("item_B"),
        ]
    )

    await w.receber_eventos(conexao, fila_saida, fila_microfone)

    itens = []
    while not fila_saida.empty():
        itens.append(fila_saida.get_nowait()[0])

    checar(
        itens == ["item_B"],
        f"o resto da fala cortada é descartado, a resposta nova toca ({itens})",
    )

    checar(
        not fila_microfone.empty(),
        "com interrupção, o áudio do usuário NÃO é jogado fora durante a fala",
    )

    checar(len(conexao.truncates) == 1, "exatamente um truncate")

    w2, _ = novo_worker(False)
    fila_saida2 = asyncio.Queue()
    fila_microfone2 = asyncio.Queue()
    fila_microfone2.put_nowait(b"eco")

    conexao2 = ConexaoFalsa([delta("item_X"), fala_do_usuario()])

    await w2.receber_eventos(conexao2, fila_saida2, fila_microfone2)

    checar(
        fila_saida2.qsize() == 1,
        "sem interrupção, a fala do usuário não corta nada",
    )
    checar(conexao2.truncates == [], "sem interrupção, nenhum truncate")
    checar(
        fila_microfone2.empty(),
        "sem interrupção, o microfone continua sendo limpo como antes",
    )
    checar(w2.interrupcoes_na_chamada == 0, "sem interrupção, contador em 0")

    w3, _ = novo_worker(True)
    w3.alfred_falando = False
    conexao3 = ConexaoFalsa([fala_do_usuario()])

    await w3.receber_eventos(conexao3, asyncio.Queue(), asyncio.Queue())

    checar(
        w3.interrupcoes_na_chamada == 0,
        "com o ALFRED calado, a fala do usuário não conta como interrupção",
    )


async def principal():
    parte1_configuracao()
    parte2_microfone()
    await parte3_corte()
    await parte4_eventos()


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
