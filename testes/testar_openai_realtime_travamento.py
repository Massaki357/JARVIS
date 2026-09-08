"""
Verificação das proteções contra travamento no worker da OpenAI
Realtime (jarvis/cerebro/openai_realtime/cliente_realtime.py).

Rodar com o venv ativo, da raiz do projeto:

    python testes/testar_openai_realtime_travamento.py

100% OFFLINE: nenhuma parte abre conexão com a OpenAI, microfone ou
alto-falante. A sessão é uma conexão falsa cujos envios podem ser
configurados para pendurar para sempre — que é exatamente o cenário
que travava a chamada inteira.

Cobre duas correções:

  ETAPA 1 — _enviar_para_sessao: todo envio tem timeout, marca
            self.conexao_travada e SOLTA o self.lock_envio. Sem isso,
            um envio pendurado segurava a trava para sempre e nenhuma
            chamada de função conseguia responder o próprio
            function_call_output — e o protocolo não deixa o modelo
            voltar a falar sem essa resposta.

  ETAPA 2 — self.tarefas_funcao_ativas: toda tarefa de chamada de
            função fica referenciada (o asyncio só mantém referência
            fraca a uma task rodando, então uma task esquecida pode
            ser coletada no meio do caminho), é removida ao terminar,
            e o limite simultâneo recusa RESPONDENDO, nunca em
            silêncio.
"""
import asyncio
import os
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Qt sem janela: o worker herda de QThread e precisa de um
# QCoreApplication existindo para ser construído com segurança.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.cerebro.openai_realtime import cliente_realtime
from jarvis.cerebro.openai_realtime.cliente_realtime import (
    LIMITE_TAREFAS_FUNCAO_SIMULTANEAS,
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


# ====================================================================
# CONEXÃO FALSA
# ====================================================================


class EnvioFalso:
    """Um endpoint de envio da sessão (item.create, response.create,
    input_audio_buffer.append). Registra o que recebeu e, se
    pendurar=True, nunca devolve."""

    def __init__(self, dono, rotulo):
        self.dono = dono
        self.rotulo = rotulo

    async def __call__(self, **kwargs):
        self.dono.enviados.append((self.rotulo, kwargs))

        if self.dono.pendurar:
            await asyncio.Event().wait()   # nunca resolve

        return None


class ItemFalso:
    def __init__(self, dono):
        self.create = EnvioFalso(dono, "item.create")


class ConversationFalsa:
    def __init__(self, dono):
        self.item = ItemFalso(dono)


class ResponseFalsa:
    def __init__(self, dono):
        self.create = EnvioFalso(dono, "response.create")


class ConexaoFalsa:
    def __init__(self, pendurar=False):
        self.pendurar = pendurar
        self.enviados = []
        self.conversation = ConversationFalsa(self)
        self.response = ResponseFalsa(self)

    def saidas(self, rotulo):
        return [e for e in self.enviados if e[0] == rotulo]


def novo_worker():
    """Worker construído sem tocar em rede, perfil ou disco."""
    trabalhador = OpenAIRealtimeWorker(slug_perfil="completo")
    trabalhador.lock_envio = asyncio.Lock()
    return trabalhador


# ====================================================================
# PARTE 1 — ETAPA 1: timeout em todo envio
# ====================================================================


async def parte1_timeout_de_envio():
    print("\n[1] ETAPA 1 - timeout em todo envio para a sessao")

    # Timeout curto só para o teste não levar 10s de verdade.
    original = cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS
    cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 1

    try:
        trabalhador = novo_worker()
        conexao = ConexaoFalsa(pendurar=True)

        laco = asyncio.get_running_loop()
        inicio = laco.time()

        try:
            await trabalhador._enviar_para_sessao(
                conexao.response.create()
            )
            estourou = False

        except asyncio.TimeoutError:
            estourou = True

        duracao = laco.time() - inicio

        checar(estourou, "um envio pendurado levanta TimeoutError")
        checar(
            duracao < 2.0,
            f"desiste em ~1s em vez de esperar para sempre ({duracao:.2f}s)",
        )
        checar(
            trabalhador.conexao_travada,
            "marca self.conexao_travada",
        )

        # Envio normal: não marca nada.
        trabalhador_ok = novo_worker()
        conexao_ok = ConexaoFalsa(pendurar=False)

        await trabalhador_ok._enviar_para_sessao(
            conexao_ok.response.create()
        )

        checar(
            not trabalhador_ok.conexao_travada,
            "envio normal NAO marca a conexao como travada",
        )
        checar(
            len(conexao_ok.saidas("response.create")) == 1,
            "envio normal chega mesmo na sessao",
        )

    finally:
        cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS = original


# ====================================================================
# PARTE 2 — ETAPA 1: a trava de envio é SOLTA no timeout
# ====================================================================


async def parte2_trava_e_solta():
    print("\n[2] ETAPA 1 - o timeout solta o self.lock_envio")

    original = cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS
    cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 1

    try:
        trabalhador = novo_worker()
        conexao = ConexaoFalsa(pendurar=True)

        # Primeira chamada de função: vai pendurar no envio e estourar.
        primeira = asyncio.create_task(
            trabalhador.processar_chamada_de_funcao(
                conexao,
                "call_1",
                "funcao_inexistente_a",
                {},
                asyncio.Queue(),
            )
        )

        await asyncio.sleep(0.3)

        checar(
            trabalhador.lock_envio.locked(),
            "a trava fica retida enquanto o envio esta pendurado",
        )

        await asyncio.wait_for(primeira, timeout=10)

        checar(
            not trabalhador.lock_envio.locked(),
            "a trava e SOLTA depois do timeout (era o congelamento)",
        )

        # É isto que importa: uma segunda chamada de função consegue
        # adquirir a trava em vez de esperar para sempre.
        segunda = asyncio.create_task(
            trabalhador.processar_chamada_de_funcao(
                conexao,
                "call_2",
                "funcao_inexistente_b",
                {},
                asyncio.Queue(),
            )
        )

        try:
            await asyncio.wait_for(segunda, timeout=10)
            segunda_terminou = True

        except asyncio.TimeoutError:
            segunda_terminou = False
            segunda.cancel()

        checar(
            segunda_terminou,
            "uma segunda chamada de funcao NAO fica presa na trava",
        )
        checar(
            trabalhador.conexao_travada,
            "a conexao travada fica registrada para executar() encerrar",
        )

    finally:
        cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS = original


# ====================================================================
# PARTE 3 — ETAPA 2: as tarefas ficam rastreadas
# ====================================================================


async def parte3_rastreamento():
    print("\n[3] ETAPA 2 - rastreamento das tarefas de chamada de funcao")

    trabalhador = novo_worker()

    async def lenta():
        await asyncio.sleep(0.4)

    tarefa = asyncio.create_task(lenta(), name="FUNCAO:teste")
    trabalhador.tarefas_funcao_ativas.append(tarefa)
    tarefa.add_done_callback(trabalhador._ao_finalizar_tarefa_funcao)

    checar(
        len(trabalhador.tarefas_funcao_ativas) == 1,
        "a tarefa fica na lista enquanto roda (sobrevive ao GC)",
    )

    await tarefa
    await asyncio.sleep(0)   # deixa o done_callback rodar

    checar(
        len(trabalhador.tarefas_funcao_ativas) == 0,
        "a tarefa sai da lista ao terminar (a lista nao cresce)",
    )

    # Cancelamento normal não é reportado como falha.
    erros = []
    trabalhador.erro_recebido.connect(erros.append)

    tarefa_cancelada = asyncio.create_task(asyncio.sleep(5))
    trabalhador.tarefas_funcao_ativas.append(tarefa_cancelada)
    tarefa_cancelada.add_done_callback(
        trabalhador._ao_finalizar_tarefa_funcao
    )
    tarefa_cancelada.cancel()

    await asyncio.gather(tarefa_cancelada, return_exceptions=True)
    await asyncio.sleep(0)

    checar(
        not erros,
        "cancelamento normal nao vira erro na interface",
    )
    checar(
        len(trabalhador.tarefas_funcao_ativas) == 0,
        "a tarefa cancelada tambem sai da lista",
    )

    # Uma exceção que escape aparece, em vez de sumir em silêncio.
    async def explode():
        raise RuntimeError("falha simulada")

    tarefa_erro = asyncio.create_task(explode(), name="FUNCAO:explode")
    trabalhador.tarefas_funcao_ativas.append(tarefa_erro)
    tarefa_erro.add_done_callback(trabalhador._ao_finalizar_tarefa_funcao)

    await asyncio.gather(tarefa_erro, return_exceptions=True)
    await asyncio.sleep(0)

    checar(
        len(erros) == 1 and "explode" in erros[0],
        "excecao que escapa e reportada, nao engolida",
    )


# ====================================================================
# PARTE 4 — ETAPA 2: o limite recusa RESPONDENDO
# ====================================================================


async def parte4_limite_simultaneo():
    print("\n[4] ETAPA 2 - limite simultaneo recusa respondendo")

    trabalhador = novo_worker()
    conexao = ConexaoFalsa()

    await trabalhador._recusar_chamada_de_funcao(
        conexao,
        "call_recusada",
        "abrir_aplicativo",
    )

    saidas = conexao.saidas("item.create")

    checar(
        len(saidas) == 1,
        "a recusa envia exatamente um function_call_output",
    )

    item = saidas[0][1].get("item", {}) if saidas else {}

    checar(
        item.get("type") == "function_call_output",
        "o tipo enviado e function_call_output",
    )
    checar(
        item.get("call_id") == "call_recusada",
        "responde o MESMO call_id (senao o modelo espera para sempre)",
    )
    checar(
        "NÃO tente de novo sozinho" in item.get("output", ""),
        "o texto manda nao repetir a chamada sozinho",
    )
    checar(
        len(conexao.saidas("response.create")) == 1,
        "libera o modelo para falar com um response.create",
    )
    checar(
        LIMITE_TAREFAS_FUNCAO_SIMULTANEAS == 4,
        "o limite simultaneo e 4, igual ao worker do Gemini",
    )


# ====================================================================
# PARTE 5 — caminho normal permanece intacto
# ====================================================================


async def parte5_caminho_normal():
    print("\n[5] REGRESSAO - o caminho rapido nao mudou")

    trabalhador = novo_worker()
    conexao = ConexaoFalsa()

    await trabalhador.processar_chamada_de_funcao(
        conexao,
        "call_ok",
        "funcao_que_nao_existe",
        {},
        asyncio.Queue(),
    )

    saidas = conexao.saidas("item.create")

    checar(
        len(saidas) == 1,
        "uma chamada normal envia exatamente um function_call_output",
    )
    checar(
        bool(saidas) and saidas[0][1]["item"]["call_id"] == "call_ok",
        "responde o call_id certo",
    )
    checar(
        len(conexao.saidas("response.create")) == 1,
        "envia exatamente um response.create",
    )
    checar(
        not trabalhador.conexao_travada,
        "o caminho normal nao marca a conexao como travada",
    )
    checar(
        not trabalhador.processando_ferramenta,
        "processando_ferramenta volta a False no fim",
    )


# ====================================================================


async def principal():
    await parte1_timeout_de_envio()
    await parte2_trava_e_solta()
    await parte3_rastreamento()
    await parte4_limite_simultaneo()
    await parte5_caminho_normal()


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
