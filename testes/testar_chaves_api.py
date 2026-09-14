import ast
import os
import sys
import tempfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

RAIZ = Path(__file__).resolve().parent.parent

falhas = []
passou = 0

CHAVES = ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY")


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


def parte1_main_verifica_antes_de_importar_o_app():
    titulo("1. main.py verifica as chaves antes de importar o app")

    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))

    modulos_topo = {
        no.module
        for no in arvore.body
        if isinstance(no, ast.ImportFrom)
    }

    checar(
        "jarvis.ui.janela_principal" not in modulos_topo
        and "jarvis.pacotes" not in modulos_topo,
        "o topo do main.py não importa a janela principal nem pacotes "
        f"(importa: {sorted(m for m in modulos_topo if m)})",
    )

    funcao_main = next(
        no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "main"
    )

    ordem = []

    for no in ast.walk(funcao_main):
        if isinstance(no, ast.ImportFrom):
            ordem.append((no.lineno, no.module))

        if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "garantir_chaves_api":
            ordem.append((no.lineno, "CHAMADA"))

    ordem.sort()
    nomes = [nome for _, nome in ordem]

    checar(
        "CHAMADA" in nomes
        and nomes.index("CHAMADA") < nomes.index("jarvis.ui.janela_principal"),
        "garantir_chaves_api() roda antes do import da janela principal",
    )


def parte2_quais_chaves_sao_basicas():
    titulo("2. Quais chaves são básicas, por cérebro")

    from jarvis.nucleo import chaves_api, config

    original_provedor = config.provedor_ativo
    original_sob_demanda = config.FERRAMENTAS_SOB_DEMANDA

    try:
        casos = (
            ("gemini", True, ["GEMINI_API_KEY", "GROQ_API_KEY"]),
            ("openai", True, ["OPENAI_API_KEY", "GROQ_API_KEY"]),
            ("local", True, ["GROQ_API_KEY"]),
            ("local", False, ["GROQ_API_KEY"]),
            ("gemini", False, ["GEMINI_API_KEY"]),
        )

        for provedor, sob_demanda, esperadas in casos:
            config.provedor_ativo = lambda provedor=provedor: provedor
            config.FERRAMENTAS_SOB_DEMANDA = sob_demanda

            checar(
                chaves_api.chaves_necessarias() == esperadas,
                f"cérebro {provedor}, sob demanda={sob_demanda}: {esperadas}",
            )

    finally:
        config.provedor_ativo = original_provedor
        config.FERRAMENTAS_SOB_DEMANDA = original_sob_demanda


def parte3_varredura_do_env():
    titulo("3. Varredura do .env acha só as que faltam")

    from jarvis.nucleo import chaves_api, config

    salvas = {nome: os.environ.pop(nome, None) for nome in CHAVES}
    original_caminho = chaves_api.CAMINHO_ENV
    original_provedor = config.provedor_ativo
    original_sob_demanda = config.FERRAMENTAS_SOB_DEMANDA

    pasta = Path(tempfile.mkdtemp())
    env = pasta / ".env"

    try:
        chaves_api.CAMINHO_ENV = env
        config.provedor_ativo = lambda: "gemini"
        config.FERRAMENTAS_SOB_DEMANDA = True

        checar(
            chaves_api.chaves_faltando() == ["GEMINI_API_KEY", "GROQ_API_KEY"],
            "sem .env: as duas chaves básicas faltam",
        )

        env.write_text("GEMINI_API_KEY=valor-de-teste\nGROQ_API_KEY=\n", encoding="utf-8")

        checar(
            chaves_api.chaves_faltando() == ["GROQ_API_KEY"],
            "chave em branco no .env conta como faltando",
        )

        os.environ["GROQ_API_KEY"] = "valor-de-teste"

        checar(
            chaves_api.chaves_faltando() == [],
            "chave definida no ambiente do sistema conta como presente",
        )

    finally:
        chaves_api.CAMINHO_ENV = original_caminho
        config.provedor_ativo = original_provedor
        config.FERRAMENTAS_SOB_DEMANDA = original_sob_demanda

        for nome, valor in salvas.items():
            os.environ.pop(nome, None)

            if valor is not None:
                os.environ[nome] = valor


def parte4_tela_mostra_so_as_que_faltam_e_salva():
    titulo("4. Tela mostra só os campos que faltam e grava no .env")

    from jarvis.nucleo import chaves_api, config
    from jarvis.pacotes.configuracoes import env_io
    from jarvis.ui import janela_chaves_api

    janela = janela_chaves_api.JanelaChavesApi(["GROQ_API_KEY"])
    campos = janela.findChildren(QLineEdit)

    checar(len(campos) == 1, f"uma chave faltando: um campo só ({len(campos)})")

    checar(
        campos and campos[0].echoMode() == QLineEdit.EchoMode.Password,
        "o campo começa mascarado",
    )

    textos = " ".join(rotulo.text() for rotulo in janela.findChildren(QLabel))

    checar(
        "GROQ_API_KEY" in textos and "GEMINI_API_KEY" not in textos,
        "a tela cita só a chave que falta",
    )

    pasta = Path(tempfile.mkdtemp())
    env = pasta / ".env"
    env.write_text("# comentário que precisa sobreviver\nOUTRA=1\n", encoding="utf-8")

    original_env_io = env_io.CAMINHO_ENV
    salva = os.environ.pop("GEMINI_API_KEY", None)

    try:
        env_io.CAMINHO_ENV = env

        janela = janela_chaves_api.JanelaChavesApi(["GEMINI_API_KEY"])
        janela.campos[0].campo.setText("  valor-gemini-de-teste  ")
        janela._salvar()

        conteudo = env.read_text(encoding="utf-8")

        checar(
            "GEMINI_API_KEY=valor-gemini-de-teste" in conteudo
            and "# comentário que precisa sobreviver" in conteudo
            and "OUTRA=1" in conteudo,
            "gravou a chave sem espaços e preservou o resto do .env",
        )

        chaves_api.aplicar_no_processo(janela.salvas)

        checar(
            config.GEMINI_API_KEY == "valor-gemini-de-teste",
            "a chave salva já vale nesta execução (config recarregado)",
        )

    finally:
        env_io.CAMINHO_ENV = original_env_io
        os.environ.pop("GEMINI_API_KEY", None)

        if salva is not None:
            os.environ["GEMINI_API_KEY"] = salva

        import importlib

        importlib.reload(config)

    original_faltando = chaves_api.chaves_faltando
    chaves_api.chaves_faltando = lambda: []

    try:
        checar(
            janela_chaves_api.garantir_chaves_api() == [],
            "com todas as chaves presentes, nenhuma tela é aberta",
        )

    finally:
        chaves_api.chaves_faltando = original_faltando


def parte5_configuracoes_rotulo_em_cima():
    titulo("5. Tela de configurações: descrição em cima, campo embaixo")

    from jarvis.pacotes.configuracoes.window import ConfiguracoesWindow, _SecaoRecolhivel

    janela = ConfiguracoesWindow()
    secao = janela.findChildren(_SecaoRecolhivel)[0]
    formulario = secao.form()

    blocos_ok = 0
    total = formulario.rowCount()

    for linha in range(total):
        item = formulario.itemAt(linha, formulario.ItemRole.SpanningRole)
        bloco = item.widget() if item else None
        layout = bloco.layout() if bloco else None

        if (
            layout is not None
            and layout.count() == 2
            and isinstance(layout.itemAt(0).widget(), QLabel)
            and layout.itemAt(0).widget().wordWrap()
        ):
            blocos_ok += 1

    checar(
        total > 0 and blocos_ok == total,
        f"todas as {total} linhas da primeira seção são rótulo em cima + campo embaixo",
    )


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])

    parte1_main_verifica_antes_de_importar_o_app()
    parte2_quais_chaves_sao_basicas()
    parte3_varredura_do_env()
    parte4_tela_mostra_so_as_que_faltam_e_salva()
    parte5_configuracoes_rotulo_em_cima()

    print("\n" + "=" * 60)

    if falhas:
        print(f"{passou} verificacoes passaram, {len(falhas)} FALHARAM:")

        for f in falhas:
            print(f"  - {f}")

        sys.exit(1)

    print(f"{passou} verificacoes passaram. Nenhuma falha.")
