import json
import subprocess
from pathlib import Path

# Rodado solto pela Tarefa Agendada, sem jarvis no sys.path: por isso parents[3].
_RAIZ_PROJETO = Path(__file__).resolve().parents[3]
# Tem que apontar para a mesma pasta de PASTA_FILA em admin_terminal/config.py.
_PASTA_FILA = _RAIZ_PROJETO / "dados" / "admin_fila"
_ARQUIVO_PEDIDO = _PASTA_FILA / "pedido_pendente.json"
_ARQUIVO_RESULTADO_TMP = _PASTA_FILA / "resultado_pendente.json.tmp"
_ARQUIVO_RESULTADO = _PASTA_FILA / "resultado_pendente.json"


def main():
    if not _ARQUIVO_PEDIDO.exists():
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

    processo = None

    try:
        processo = subprocess.Popen(
            ["cmd.exe", "/d", "/c", comando],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        stdout, stderr = processo.communicate(
            timeout=timeout_segundos
        )

        _escrever_resultado(
            {
                "sucesso": processo.returncode == 0,
                "codigo_saida": processo.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    except subprocess.TimeoutExpired:
        if processo is not None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(processo.pid)],
                capture_output=True,
            )

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


def _escrever_resultado(dados):
    _ARQUIVO_RESULTADO_TMP.write_text(
        json.dumps(dados),
        encoding="utf-8",
    )
    _ARQUIVO_RESULTADO_TMP.replace(_ARQUIVO_RESULTADO)


if __name__ == "__main__":
    main()
