# Fecha um app já resolvido pelo nome real do processo (vindo de
# processos.buscar_processo) — nunca aceita nome/comando/caminho
# arbitrário vindo direto da fala do usuário, só um nome de processo
# que o próprio psutil já enxerga rodando de verdade.
#
# Fechamento GRACIOSO primeiro: manda WM_CLOSE pra(s) janela(s)
# principal(is) do processo, dando chance dele perguntar "salvar
# antes de fechar?" se tiver essa lógica própria. Só recorre a
# terminate()/kill() se o processo não tiver nenhuma janela visível
# (rodando em segundo plano) ou não responder ao WM_CLOSE dentro de
# TIMEOUT_FECHAMENTO_GRACIOSO_SEGUNDOS.
import os
import time

import psutil
import win32con
import win32gui
import win32process

# Processos que o ALFRED NUNCA fecha, custe o que custar — núcleo do
# próprio Windows. Comparação sempre em minúsculas.
PROCESSOS_PROTEGIDOS = {
    "explorer.exe",
    "winlogon.exe",
    "csrss.exe",
    "services.exe",
    "svchost.exe",
}

# Tempo, em segundos, que um processo tem pra responder ao WM_CLOSE
# (fechamento gracioso) antes de ser considerado sem resposta e
# finalizado à força.
TIMEOUT_FECHAMENTO_GRACIOSO_SEGUNDOS = 5

# Intervalo entre verificações de "o processo já fechou?" durante a
# espera graciosa.
INTERVALO_VERIFICACAO_SEGUNDOS = 0.2

# Tempo de espera, em segundos, depois de terminate()/kill() — dá uma
# chance curta ao Windows de liberar o processo antes de reportar
# falha.
TIMEOUT_FECHAMENTO_FORCADO_SEGUNDOS = 2


# nome_processo já é o nome REAL de um processo em execução (vindo de
# processos.buscar_processo) — nunca comparado por prefixo/regex
# solto, só igualdade exata (case-insensitive) contra a lista fixa
# acima. O próprio processo do ALFRED (este interpretador em execução
# agora) é protegido à parte, por PID — nunca por nome, porque
# bloquear "python.exe"/"pythonw.exe" de forma genérica fecharia a
# porta pra qualquer outro processo Python do usuário que nada tenha
# a ver com o ALFRED.
def _e_processo_protegido(nome_processo, pid):
    if nome_processo.lower() in PROCESSOS_PROTEGIDOS:
        return True

    if pid == os.getpid():
        return True

    return False


# Janelas visíveis e com título pertencentes a este PID — só essas
# contam como "janela principal" pra fins de WM_CLOSE (uma janela sem
# título costuma ser um componente interno, não a janela que o
# usuário reconheceria como o programa aberto).
def _janelas_principais_do_pid(pid):
    handles = []

    def _callback(hwnd, _lparam):
        if not win32gui.IsWindowVisible(hwnd):
            return True

        if not win32gui.GetWindowText(hwnd):
            return True

        _, pid_da_janela = win32process.GetWindowThreadProcessId(hwnd)

        if pid_da_janela == pid:
            handles.append(hwnd)

        return True

    win32gui.EnumWindows(_callback, None)

    return handles


def _pids_por_nome(nome_processo):
    pids = []

    for processo in psutil.process_iter(["pid", "name"]):
        try:
            if processo.info.get("name") == nome_processo:
                pids.append(processo.info["pid"])

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return pids


def _fechar_um_processo(pid):
    """Fecha um único PID (gracioso, depois forçado se preciso).
    Retorna "gracioso", "forcado" ou "falha"."""
    try:
        processo = psutil.Process(pid)

    except psutil.NoSuchProcess:
        return "gracioso"

    handles = _janelas_principais_do_pid(pid)

    for hwnd in handles:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

        except Exception:
            pass

    if handles:
        limite = time.monotonic() + TIMEOUT_FECHAMENTO_GRACIOSO_SEGUNDOS

        while time.monotonic() < limite:
            if not processo.is_running():
                return "gracioso"

            time.sleep(INTERVALO_VERIFICACAO_SEGUNDOS)

    # Sem janela visível (processo em segundo plano) ou não respondeu
    # ao WM_CLOSE a tempo — força o fechamento.
    try:
        processo.terminate()

    except psutil.NoSuchProcess:
        return "forcado"

    except Exception:
        return "falha"

    try:
        processo.wait(timeout=TIMEOUT_FECHAMENTO_FORCADO_SEGUNDOS)
        return "forcado"

    except psutil.TimeoutExpired:
        try:
            processo.kill()
            processo.wait(timeout=TIMEOUT_FECHAMENTO_FORCADO_SEGUNDOS)
            return "forcado"

        except Exception:
            return "falha"

    except psutil.NoSuchProcess:
        return "forcado"


# Fecha TODOS os processos com o nome exato nome_processo (pode ser
# mais de um — ex: várias janelas do mesmo navegador, cada uma seu
# próprio processo). Retorna uma mensagem em português pronta pra
# falar, nunca lança exceção.
def fechar_processos_por_nome(nome_processo):
    pids = _pids_por_nome(nome_processo)

    if not pids:
        return f"Não encontrei nenhum processo '{nome_processo}' em execução."

    for pid in pids:
        if _e_processo_protegido(nome_processo, pid):
            return (
                f"'{nome_processo}' é um processo protegido do sistema "
                "(ou o próprio ALFRED) — não posso fechar isso, nem "
                "de forma normal nem à força."
            )

    fechados_gracioso = 0
    fechados_forcado = 0
    falhas = 0

    for pid in pids:
        resultado = _fechar_um_processo(pid)

        if resultado == "gracioso":
            fechados_gracioso += 1

        elif resultado == "forcado":
            fechados_forcado += 1

        else:
            falhas += 1

    total_fechados = fechados_gracioso + fechados_forcado

    if total_fechados == 0:
        return (
            f"Não consegui fechar '{nome_processo}' "
            f"({falhas} processo(s) resistiram)."
        )

    partes = []

    if fechados_gracioso:
        partes.append(f"{fechados_gracioso} fechado(s) normalmente")

    if fechados_forcado:
        partes.append(f"{fechados_forcado} fechado(s) à força")

    mensagem = f"'{nome_processo}': " + ", ".join(partes) + "."

    if falhas:
        mensagem += f" {falhas} processo(s) não puderam ser fechados."

    return mensagem
