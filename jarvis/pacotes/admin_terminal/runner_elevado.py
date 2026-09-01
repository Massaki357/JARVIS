# Este script SÓ é executado pela Tarefa Agendada do Windows criada
# por 'python -m jarvis.pacotes.admin_terminal.setup' — nunca é chamado diretamente
# pelo resto do jarvis. Roda com privilégio de administrador
# (RunLevel HIGHEST configurado na tarefa), lê o pedido pendente
# deixado por executor.py em dados/admin_fila/pedido_pendente.json,
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

# Este script e iniciado pela Tarefa Agendada com o caminho
# completo do arquivo (pythonw.exe <caminho>/runner_elevado.py),
# entao a raiz do projeto NAO esta no sys.path e "jarvis" nao pode
# ser importado aqui -- por isso a pasta e recalculada na mao, em
# vez de vir de jarvis/caminhos.py. Precisa apontar para o mesmo
# lugar que PASTA_FILA em jarvis/pacotes/admin_terminal/config.py: se um dos dois
# mudar, o outro tem que mudar junto.
#
#   jarvis/pacotes/admin_terminal/runner_elevado.py
#     -> parents[3] = raiz do projeto
_RAIZ_PROJETO = Path(__file__).resolve().parents[3]
_PASTA_FILA = _RAIZ_PROJETO / "dados" / "admin_fila"
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

    processo = None

    try:
        # /d desativa comandos AutoRun do registro do cmd.exe — evita
        # que algo configurado ali rode de surpresa junto do comando
        # pedido, mesmo estando num processo já elevado.
        #
        # stdin=DEVNULL: BUG REAL corrigido aqui, confirmado ao vivo —
        # sem isso, um comando que tenta ler de stdin (ex: 'winget
        # upgrade' pedindo pra aceitar um termo de licença/fonte na
        # primeira execução) fica esperando uma entrada que nunca
        # chega. Essa espera é síncrona e bloqueante dentro do
        # processo elevado, que por sua vez trava executor.py (que
        # está esperando o resultado numa thread do worker do
        # jarvis) — travando o app inteiro, sem timeout nenhum
        # conseguir resolver isso sozinho (ver o tratamento de
        # TimeoutExpired abaixo, que também precisou de correção pelo
        # mesmo motivo). Com DEVNULL, esse tipo de comando recebe EOF
        # na hora e falha rápido em vez de travar pra sempre. Foi
        # exatamente isso que aconteceu com 'winget upgrade --all':
        # travou o app inteiro, sem responder, sem conseguir encerrar
        # a chamada nem fechar o app — só resolvia pelo Gerenciador de
        # Tarefas.
        #
        # creationflags=CREATE_NO_WINDOW: evita a janela de console
        # preta e visível na área de trabalho — o processo elevado em
        # si (python.exe rodando este script, via Tarefa Agendada) já
        # aloca console próprio; sem essa flag, o cmd.exe filho abria
        # mais uma janela por cima.
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
        # cmd.exe pode ter processos filhos próprios (ex: winget.exe)
        # que não morrem só matando o cmd.exe — mata a árvore inteira
        # (/T) pra garantir que nada fique órfão rodando (ou segurando
        # os pipes de stdout/stderr abertos, o que travaria a leitura
        # do resultado mesmo depois do timeout). BUG REAL confirmado
        # ao vivo, junto com o stdin=DEVNULL acima.
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


# Escrita atômica (escreve em .tmp, depois renomeia) — mesma
# convenção usada em jarvis/servicos/memoria/gerenciador.py, pra executor.py nunca
# ler um resultado.json pela metade.
def _escrever_resultado(dados):
    _ARQUIVO_RESULTADO_TMP.write_text(
        json.dumps(dados),
        encoding="utf-8",
    )
    _ARQUIVO_RESULTADO_TMP.replace(_ARQUIVO_RESULTADO)


if __name__ == "__main__":
    main()
