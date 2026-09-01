# Executa comandos com privilégio de administrador via a Tarefa
# Agendada criada por 'python -m jarvis.pacotes.admin_terminal.setup' (ver
# setup.py e runner_elevado.py), e registra o log local de tudo que
# roda com privilégio elevado.
#
# Mecanismo: este processo (privilégio normal) escreve o comando num
# arquivo de "pedido" na pasta _fila, dispara a tarefa via
# 'schtasks /run' (que já está configurada com RunLevel HIGHEST — não
# pede UAC de novo, só na criação da tarefa), e espera o processo
# elevado (runner_elevado.py, iniciado pela própria tarefa) escrever
# o "resultado" de volta. Um único comando por vez (protegido por
# _lock_execucao) — não há necessidade de suportar execuções
# administrativas concorrentes neste projeto.
import json
import subprocess
import threading
import time
from datetime import datetime

from . import config

_lock_execucao = threading.Lock()

_ARQUIVO_PEDIDO = config.PASTA_FILA / "pedido_pendente.json"
_ARQUIVO_RESULTADO = config.PASTA_FILA / "resultado_pendente.json"

config.PASTA_FILA.mkdir(parents=True, exist_ok=True)


# Ponto único usado por confirmacao.py para os dois caminhos (voz e
# notificação) depois que o usuário confirmou ou negou. Sempre
# registra no log, mesmo quando negado.
def executar_comando_confirmado(comando, confirmado, execucao_longa, origem):
    if not confirmado:
        registrar_log(
            comando,
            automatico=False,
            sucesso=False,
            resumo=f"Negado pelo usuário (canal: {origem}).",
        )

        return f"Comando '{comando}' não foi confirmado — não foi executado."

    timeout = (
        config.TIMEOUT_COMANDO_LONGO_SEGUNDOS
        if execucao_longa
        else config.TIMEOUT_PADRAO_SEGUNDOS
    )

    sucesso, resultado = executar_via_tarefa_agendada(comando, timeout)

    registrar_log(
        comando,
        automatico=False,
        sucesso=sucesso,
        resumo=resultado,
    )

    if sucesso:
        return (
            f"Comando '{comando}' confirmado e executado com "
            f"sucesso. {resultado}"
        ).strip()

    return f"Comando '{comando}' confirmado, mas falhou ao executar: {resultado}"


# Dispara o comando na tarefa elevada e espera o resultado. Retorna
# (sucesso: bool, mensagem: str) — nunca lança exceção, mesma
# convenção usada em jarvis/pacotes/casa_inteligente/tuya_client.py e
# jarvis/servicos/email/remetente.py.
def executar_via_tarefa_agendada(comando, timeout_segundos):
    with _lock_execucao:
        _limpar_arquivos_fila()

        try:
            _ARQUIVO_PEDIDO.write_text(
                json.dumps(
                    {
                        "comando": comando,
                        "timeout_segundos": timeout_segundos,
                    }
                ),
                encoding="utf-8",
            )

        except OSError as erro:
            return False, f"Falha ao preparar o pedido: {erro}"

        disparo = subprocess.run(
            ["schtasks", "/run", "/tn", config.NOME_TAREFA_AGENDADA],
            capture_output=True,
            text=True,
        )

        if disparo.returncode != 0:
            _limpar_arquivos_fila()

            return False, (
                "Falha ao disparar a tarefa agendada de "
                f"administrador ('{config.NOME_TAREFA_AGENDADA}'): "
                f"{(disparo.stderr or disparo.stdout).strip()}. Ela "
                "existe? Rode 'python -m jarvis.pacotes.admin_terminal.setup' se "
                "ainda não configurou."
            )

        limite = time.monotonic() + timeout_segundos + config.MARGEM_ESPERA_TAREFA_SEGUNDOS

        while time.monotonic() < limite:
            if _ARQUIVO_RESULTADO.exists():
                break

            time.sleep(0.3)

        else:
            _limpar_arquivos_fila()

            return False, (
                "A tarefa agendada não respondeu a tempo — verifique "
                "se ela foi criada corretamente ('python -m "
                "admin_terminal.setup') e se está com RunLevel "
                "'Highest'."
            )

        try:
            dados = json.loads(
                _ARQUIVO_RESULTADO.read_text(encoding="utf-8")
            )

        except (OSError, json.JSONDecodeError) as erro:
            _limpar_arquivos_fila()

            return False, f"Falha ao ler o resultado da tarefa agendada: {erro}"

        _limpar_arquivos_fila()

        return _formatar_resultado(dados)


def _formatar_resultado(dados):
    if dados.get("erro"):
        return False, dados["erro"]

    sucesso = bool(dados.get("sucesso"))
    stdout = (dados.get("stdout") or "").strip()
    stderr = (dados.get("stderr") or "").strip()

    if sucesso:
        return True, (stdout[-500:] if stdout else "Sem saída.")

    return False, (stderr or stdout or "Falhou sem detalhes de erro.")[-500:]


def _limpar_arquivos_fila():
    for caminho in (_ARQUIVO_PEDIDO, _ARQUIVO_RESULTADO):
        try:
            caminho.unlink()

        except OSError:
            pass


# Mantém o log sob um teto simples de tamanho: se já passou de
# config.LIMITE_TAMANHO_LOG_BYTES, descarta a metade mais antiga das
# linhas e regrava só a metade mais recente. Chamado antes de cada
# escrita (registrar_log, abaixo) — o stat() é barato o bastante pra
# rodar em toda escrita sem custo perceptível. Nunca lança exceção: um
# log que não pôde ser aparado continua sendo usado do jeito que está,
# só cresce um pouco mais até a próxima tentativa.
def _aparar_log_se_necessario():
    try:
        if config.ARQUIVO_LOG.stat().st_size <= config.LIMITE_TAMANHO_LOG_BYTES:
            return

        with open(config.ARQUIVO_LOG, "r", encoding="utf-8", errors="replace") as arquivo:
            linhas = arquivo.readlines()

        linhas_mantidas = linhas[len(linhas) // 2:]

        with open(config.ARQUIVO_LOG, "w", encoding="utf-8") as arquivo:
            arquivo.writelines(linhas_mantidas)

    except OSError as erro:
        print(f"[admin_terminal] Falha ao aparar o log: {erro}")


# Log local, texto simples, append-only. Nunca girado em vários
# arquivos nem apagado por completo — só aparado (ver
# _aparar_log_se_necessario) quando passa de
# config.LIMITE_TAMANHO_LOG_BYTES, pra nunca crescer sem limite.
def registrar_log(comando, automatico, sucesso, resumo):
    linha = (
        f"{datetime.now().isoformat(timespec='seconds')} | "
        f"{'AUTOMATICO' if automatico else 'CONFIRMADO'} | "
        f"{'OK' if sucesso else 'FALHA'} | "
        f"{comando} | "
        f"{(resumo or '').replace(chr(10), ' ').replace(chr(13), '')[:300]}\n"
    )

    _aparar_log_se_necessario()

    try:
        with open(config.ARQUIVO_LOG, "a", encoding="utf-8") as arquivo:
            arquivo.write(linha)

    except OSError as erro:
        print(f"[admin_terminal] Falha ao gravar log: {erro}")
