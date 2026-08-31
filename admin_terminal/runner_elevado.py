# Este script SÓ é executado pela Tarefa Agendada do Windows criada
# por 'python -m admin_terminal.setup' — nunca é chamado diretamente
# pelo resto do jarvis. Roda com privilégio de administrador
# (RunLevel HIGHEST configurado na tarefa), lê o pedido pendente
# deixado por executor.py em admin_terminal/_fila/pedido_pendente.json,
# executa o comando exato ali contido, e escreve o resultado de volta
# em resultado_pendente.json.
#
# Fica isolado como script próprio (em vez de uma função chamada de
# dentro do processo principal do jarvis) porque a elevação via
# Tarefa Agendada só eleva o PROCESSO que ela mesma inicia — não pode
# elevar um processo já em execução.
import json
import subprocess
from pathlib import Path

_PASTA_FILA = Path(__file__).resolve().parent / "_fila"
_ARQUIVO_PEDIDO = _PASTA_FILA / "pedido_pendente.json"
_ARQUIVO_RESULTADO_TMP = _PASTA_FILA / "resultado_pendente.json.tmp"
_ARQUIVO_RESULTADO = _PASTA_FILA / "resultado_pendente.json"


def main():
    if not _ARQUIVO_PEDIDO.exists():
        # Nada pendente — a tarefa pode ter sido disparada manualmente
        # para teste (ver instruções de setup.py). Não é um erro.
        return

    try:
        pedido = json.loads(_ARQUIVO_PEDIDO.read_text(encoding="utf-8"))

    except (OSError, json.JSONDecodeError) as erro:
        _escrever_resultado({"sucesso": False, "erro": f"Falha ao ler pedido: {erro}"})
        return

    comando = pedido.get("comando", "")
    timeout_segundos = pedido.get("timeout_segundos", 30)

    if not comando:
        _escrever_resultado({"sucesso": False, "erro": "Pedido sem comando."})
        return

    try:
        # /d desativa comandos AutoRun do registro do cmd.exe — evita
        # que algo configurado ali rode de surpresa junto do comando
        # pedido, mesmo estando num processo já elevado.
        processo = subprocess.run(
            ["cmd.exe", "/d", "/c", comando],
            capture_output=True,
            text=True,
            timeout=timeout_segundos,
        )

        _escrever_resultado(
            {
                "sucesso": processo.returncode == 0,
                "codigo_saida": processo.returncode,
                "stdout": processo.stdout,
                "stderr": processo.stderr,
            }
        )

    except subprocess.TimeoutExpired:
        _escrever_resultado(
            {"sucesso": False, "erro": "Tempo limite excedido durante a execução."}
        )

    except Exception as erro:
        _escrever_resultado({"sucesso": False, "erro": str(erro)})

    finally:
        try:
            _ARQUIVO_PEDIDO.unlink()

        except OSError:
            pass


# Escrita atômica (escreve em .tmp, depois renomeia) — mesma
# convenção usada em memory/memory_manager.py, pra executor.py nunca
# ler um resultado.json pela metade.
def _escrever_resultado(dados):
    _ARQUIVO_RESULTADO_TMP.write_text(
        json.dumps(dados),
        encoding="utf-8",
    )
    _ARQUIVO_RESULTADO_TMP.replace(_ARQUIVO_RESULTADO)


if __name__ == "__main__":
    main()
