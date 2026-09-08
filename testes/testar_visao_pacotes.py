"""
Verificação de que as tools de visão que dependem do cliente para
capturar a imagem funcionam nos TRÊS cérebros de voz.

Rodar com o venv ativo, da raiz do projeto:

    python testes/testar_visao_pacotes.py

100% OFFLINE: nenhuma parte chama Gemini, OpenAI, Mistral ou o
alfred-server. As capturas de tela/câmera reais só são exercidas na
parte 1 (rápidas e sem efeito colateral: nada é gravado em disco).

BUG REAL que este teste tranca:

    descrever_tela / descrever_camera (jarvis/pacotes/descricao_visual/)
    nasceram para o cérebro local, e só o cliente local aprendeu a
    injetar imagem_bytes antes do despacho. Mas o pacote está em
    PACOTES_REGISTRADOS, que é GLOBAL — os três cérebros declaravam as
    duas tools, e nos workers do Gemini e da OpenAI elas falhavam
    SEMPRE com "nenhuma imagem foi capturada".

    Sintoma relatado pelo usuário: pedir para o jarvis (cérebro Gemini)
    olhar a tela, e ele responder que deu erro ao acessar a câmera e
    ver a tela — o modelo escolhia descrever_tela (quebrada) em vez da
    nativa analisar_tela (que funciona), sem ter como saber a
    diferença.
"""
import os
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jarvis.nucleo.registro_pacotes import (
    PACOTES_REGISTRADOS,
    TOOLS_QUE_PRECISAM_DE_IMAGEM,
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
# PARTE 1 — as capturas reais funcionam
# ====================================================================


def parte1_capturas():
    print("\n[1] As funcoes de captura funcionam nesta maquina")

    from jarvis.servicos.visao.captura_tela import (
        capturar_monitor_do_cursor_bytes,
    )
    from jarvis.servicos.visao.captura_camera import capturar_camera_bytes

    try:
        tela = capturar_monitor_do_cursor_bytes()
    except Exception as erro:
        tela = None
        print(f"        (captura de tela levantou: {erro!r})")

    checar(
        bool(tela) and len(tela) > 1000,
        f"captura de tela devolve JPEG ({len(tela or '')} bytes)",
    )

    try:
        camera = capturar_camera_bytes()
    except Exception as erro:
        camera = None
        print(f"        (captura de camera levantou: {erro!r})")

    checar(
        bool(camera) and len(camera) > 500,
        f"captura de camera devolve JPEG ({len(camera or '')} bytes)",
    )


# ====================================================================
# PARTE 2 — a lista cobre toda tool que precisa de imagem
# ====================================================================


def parte2_lista_completa():
    print("\n[2] TOOLS_QUE_PRECISAM_DE_IMAGEM cobre quem precisa")

    esperadas = {
        "identificar_planta": "camera",
        "consultar_segunda_opiniao_visual": "camera",
        "descrever_tela": "tela",
        "descrever_camera": "camera",
    }

    for nome, origem in esperadas.items():
        checar(
            TOOLS_QUE_PRECISAM_DE_IMAGEM.get(nome) == origem,
            f"{nome} esta na lista com origem '{origem}'",
        )

    checar(
        set(TOOLS_QUE_PRECISAM_DE_IMAGEM.values()) <= {"tela", "camera"},
        "toda origem e 'tela' ou 'camera' (nada mais)",
    )

    # Toda tool da lista precisa existir de verdade em algum pacote —
    # senao a lista silenciosamente aponta para nada.
    registradas = set()
    for pacote in PACOTES_REGISTRADOS:
        for decl in pacote.obter_function_declarations():
            registradas.add(decl.name)

    ausentes = set(TOOLS_QUE_PRECISAM_DE_IMAGEM) - registradas
    checar(
        not ausentes,
        f"toda tool da lista existe em um pacote registrado ({ausentes or 'ok'})",
    )


# ====================================================================
# PARTE 3 — os TRES clientes usam a MESMA lista
# ====================================================================


def parte3_tres_clientes():
    print("\n[3] Os tres cerebros usam a mesma fonte da verdade")

    from jarvis.cerebro.gemini import cliente_live
    from jarvis.cerebro.openai_realtime import cliente_realtime
    from jarvis.cerebro.voz_local import cliente_local

    checar(
        cliente_live.TOOLS_QUE_PRECISAM_DE_IMAGEM
        is TOOLS_QUE_PRECISAM_DE_IMAGEM,
        "worker do Gemini importa a lista compartilhada",
    )
    checar(
        cliente_realtime.TOOLS_QUE_PRECISAM_DE_IMAGEM
        is TOOLS_QUE_PRECISAM_DE_IMAGEM,
        "worker da OpenAI importa a lista compartilhada",
    )
    checar(
        cliente_local.FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM
        is TOOLS_QUE_PRECISAM_DE_IMAGEM,
        "worker local usa a mesma lista (nao uma copia)",
    )

    # A regressao concreta: nenhum cliente pode ter uma lista propria
    # com MENOS entradas que a compartilhada.
    fonte = Path("jarvis/cerebro/gemini/cliente_live.py").read_text(
        encoding="utf-8"
    )
    checar(
        'if nome in TOOLS_QUE_PRECISAM_DE_IMAGEM:' in fonte,
        "o worker do Gemini testa a lista, nao uma tupla fixa",
    )

    fonte_openai = Path(
        "jarvis/cerebro/openai_realtime/cliente_realtime.py"
    ).read_text(encoding="utf-8")
    checar(
        'if nome in TOOLS_QUE_PRECISAM_DE_IMAGEM:' in fonte_openai,
        "o worker da OpenAI testa a lista, nao uma tupla fixa",
    )


# ====================================================================
# PARTE 4 — descrever_* realmente responde quando recebe a imagem
# ====================================================================


def parte4_pacote_aceita_imagem():
    print("\n[4] O pacote descricao_visual reage a imagem_bytes")

    from jarvis.pacotes import descricao_visual

    # SEM imagem: e exatamente a mensagem que o usuario ouviu.
    sem = descricao_visual.despachar("descrever_tela", {"pergunta": "?"})

    checar(
        sem is not None and "nenhuma imagem foi capturada" in sem,
        "sem imagem_bytes devolve o erro que o usuario relatou",
    )

    # COM imagem: nao pode mais ser esse erro. Nao chamamos a rede —
    # basta provar que passou da checagem de imagem ausente.
    from jarvis.servicos.visao.captura_tela import (
        capturar_monitor_do_cursor_bytes,
    )

    com = descricao_visual.despachar(
        "descrever_tela",
        {"pergunta": "O que aparece?", "imagem_bytes": capturar_monitor_do_cursor_bytes()},
    )

    checar(
        com is not None and "nenhuma imagem foi capturada" not in com,
        "com imagem_bytes NAO devolve mais aquele erro",
    )

    # Nome desconhecido continua devolvendo None (contrato do pacote).
    checar(
        descricao_visual.despachar("funcao_inexistente", {}) is None,
        "nome desconhecido devolve None (contrato do pacote)",
    )


# ====================================================================


if __name__ == "__main__":
    parte1_capturas()
    parte2_lista_completa()
    parte3_tres_clientes()
    parte4_pacote_aceita_imagem()

    print("\n" + "=" * 60)

    if falhas:
        print(f"{passou} verificacoes passaram, {len(falhas)} FALHARAM:")

        for f in falhas:
            print(f"  - {f}")

        sys.exit(1)

    print(f"{passou} verificacoes passaram. Nenhuma falha.")
