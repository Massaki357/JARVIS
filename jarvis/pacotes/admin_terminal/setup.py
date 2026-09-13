import subprocess
import sys
from pathlib import Path

from . import config

_CAMINHO_RUNNER = Path(__file__).resolve().parent / "runner_elevado.py"

_EXECUTAVEL_TAREFA = Path(sys.executable).with_name("pythonw.exe")

if not _EXECUTAVEL_TAREFA.is_file():
    _EXECUTAVEL_TAREFA = Path(sys.executable)


# Só manual: nunca chamar de outro código, altera o sistema (docs/admin_terminal.md).
def criar_tarefa():
    print(
        "Isto vai criar uma Tarefa Agendada do Windows chamada "
        f"'{config.NOME_TAREFA_AGENDADA}', configurada com "
        "privilégio de administrador (RunLevel HIGHEST). A partir daí, "
        "todo comando administrativo aprovado pelo jarvis (automático "
        "ou confirmado por você) roda através dela, sem popup de UAC "
        "a cada vez.\n"
    )
    print(f"Executável Python usado pela tarefa: {_EXECUTAVEL_TAREFA}")
    print(f"Script executado pela tarefa: {_CAMINHO_RUNNER}\n")

    resposta = input("Digite SIM para criar a tarefa agora: ").strip()

    if resposta.upper() != "SIM":
        print("Cancelado — nenhuma tarefa foi criada.")
        return

    comando_acao = f'"{_EXECUTAVEL_TAREFA}" "{_CAMINHO_RUNNER}"'

    resultado = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", config.NOME_TAREFA_AGENDADA,
            "/tr", comando_acao,
            "/sc", "once",
            "/st", "00:00",
            "/rl", "highest",
            "/f",
        ],
        capture_output=True,
        text=True,
    )

    if resultado.returncode != 0:
        print("Falha ao criar a tarefa agendada:")
        print(resultado.stderr or resultado.stdout)
        sys.exit(1)

    print(f"\nTarefa '{config.NOME_TAREFA_AGENDADA}' criada com sucesso.")
    print(
        "O Windows pode ter pedido sua aprovação de administrador "
        "durante este comando — isso é esperado e só acontece agora, "
        "na criação da tarefa. As próximas execuções (via 'schtasks "
        "/run') não pedem UAC de novo.\n"
    )
    print(
        "Para testar manualmente: "
        f'schtasks /run /tn "{config.NOME_TAREFA_AGENDADA}"'
    )


def remover_tarefa():
    print(
        f"Isto vai remover a Tarefa Agendada "
        f"'{config.NOME_TAREFA_AGENDADA}' do Windows. Depois disso, "
        "comandos administrativos do jarvis vão falhar até "
        "'python -m jarvis.pacotes.admin_terminal.setup' ser rodado de novo.\n"
    )

    resposta = input(
        f"Digite SIM para REMOVER a tarefa "
        f"'{config.NOME_TAREFA_AGENDADA}': "
    ).strip()

    if resposta.upper() != "SIM":
        print("Cancelado.")
        return

    resultado = subprocess.run(
        ["schtasks", "/delete", "/tn", config.NOME_TAREFA_AGENDADA, "/f"],
        capture_output=True,
        text=True,
    )

    if resultado.returncode != 0:
        print("Falha ao remover a tarefa agendada:")
        print(resultado.stderr or resultado.stdout)
        sys.exit(1)

    print(f"Tarefa '{config.NOME_TAREFA_AGENDADA}' removida.")


if __name__ == "__main__":
    if "--remover" in sys.argv:
        remover_tarefa()
    else:
        criar_tarefa()
