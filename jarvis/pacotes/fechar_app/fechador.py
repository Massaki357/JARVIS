import os
import time

import psutil
import win32con
import win32gui
import win32process

# Nunca enfraquecer (docs/fechar_app.md).
PROCESSOS_PROTEGIDOS = {
    "explorer.exe",
    "winlogon.exe",
    "csrss.exe",
    "services.exe",
    "svchost.exe",
}

TIMEOUT_FECHAMENTO_GRACIOSO_SEGUNDOS = 5

INTERVALO_VERIFICACAO_SEGUNDOS = 0.2

TIMEOUT_FECHAMENTO_FORCADO_SEGUNDOS = 2


def _e_processo_protegido(nome_processo, pid):
    if nome_processo.lower() in PROCESSOS_PROTEGIDOS:
        return True

    if pid == os.getpid():
        return True

    return False


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
    try:
        processo = psutil.Process(pid)

    except psutil.NoSuchProcess:
        return "gracioso"

    handles = _janelas_principais_do_pid(pid)

    for hwnd in handles:
        try:
            # WM_CLOSE antes de terminate/kill: dá ao app a chance de pedir para salvar.
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

        except Exception:
            pass

    if handles:
        limite = time.monotonic() + TIMEOUT_FECHAMENTO_GRACIOSO_SEGUNDOS

        while time.monotonic() < limite:
            if not processo.is_running():
                return "gracioso"

            time.sleep(INTERVALO_VERIFICACAO_SEGUNDOS)

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
