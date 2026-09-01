# Obtém o item selecionado na ÁREA DE TRABALHO do Windows — diferente
# de uma janela do Explorer aberta (ver selecao.py): a Área de
# Trabalho não aparece na coleção Shell.Application().Windows(), é
# uma listview (SysListView32) dentro de Progman/WorkerW, pertencente
# ao processo do explorer.exe (não ao nosso próprio processo).
#
# Confirmado ao vivo, com uma seleção real feita à mão na Área de
# Trabalho, antes de considerar esta abordagem pronta — não foi
# adivinhada: LVM_GETNEXTITEM(-1, LVNI_SELECTED) devolve o índice do
# item selecionado de qualquer processo via SendMessage comum (só
# retorna um número), mas o NOME do item (LVM_GETITEMTEXTW) exige um
# buffer que precisa existir dentro do espaço de memória do processo
# DONO da listview — por isso o
# VirtualAllocEx/WriteProcessMemory/ReadProcessMemory abaixo, técnica
# clássica e documentada pra ler texto de um controle ListView de
# outro processo (a mesma usada por ferramentas de automação como o
# pywinauto).
import ctypes
from ctypes import wintypes
from pathlib import Path

import win32com.client
import win32gui
import win32process
from win32comext.shell import shell, shellcon

# Mensagens/flags de ListView usados aqui — LVM_FIRST = 0x1000.
# LVM_GETITEMTEXTW é a variante Unicode (LVM_FIRST + 115), diferente
# de LVM_GETITEMTEXT/"A" (LVM_FIRST + 45, a que o módulo commctrl do
# pywin32 costuma expor por padrão) — como lemos via SendMessageW
# explicitamente, é a constante Unicode que precisa ser usada aqui,
# por isso definida direto em vez de importada de commctrl.
_LVM_FIRST = 0x1000
_LVM_GETNEXTITEM = _LVM_FIRST + 12
_LVM_GETITEMTEXTW = _LVM_FIRST + 115
_LVNI_SELECTED = 2

_PROCESS_VM_OPERATION = 0x0008
_PROCESS_VM_READ = 0x0010
_PROCESS_VM_WRITE = 0x0020
_PROCESS_QUERY_INFORMATION = 0x0400
_MEM_COMMIT = 0x1000
_MEM_RESERVE = 0x2000
_MEM_RELEASE = 0x8000
_PAGE_READWRITE = 0x04

# Em caracteres (WCHAR) — folgado o suficiente pra qualquer nome de
# arquivo real do Windows (limite do próprio SO é 255).
_TAMANHO_BUFFER_TEXTO = 512


class _LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wintypes.UINT),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", wintypes.UINT),
        ("stateMask", wintypes.UINT),
        ("pszText", wintypes.LPWSTR),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", ctypes.c_void_p),
        ("iIndent", ctypes.c_int),
    ]


# Percorre Progman e as janelas WorkerW procurando
# SHELLDLL_DefView -> SysListView32 (no Windows moderno, a
# SHELLDLL_DefView às vezes fica numa WorkerW irmã do Progman em vez
# do próprio Progman — checa as duas). Retorna o hwnd da listview, ou
# None se não encontrar.
def _encontrar_hwnd_listview_area_trabalho():
    candidatos_pai = []

    hwnd_progman = win32gui.FindWindow("Progman", None)

    if hwnd_progman:
        candidatos_pai.append(hwnd_progman)

    def _coletar_workerw(hwnd, _lparam):
        if win32gui.GetClassName(hwnd) == "WorkerW":
            candidatos_pai.append(hwnd)
        return True

    win32gui.EnumWindows(_coletar_workerw, None)

    for pai in candidatos_pai:
        hwnd_defview = win32gui.FindWindowEx(
            pai, 0, "SHELLDLL_DefView", None
        )

        if hwnd_defview:
            hwnd_listview = win32gui.FindWindowEx(
                hwnd_defview, 0, "SysListView32", None
            )

            if hwnd_listview:
                return hwnd_listview

    return None


def _indices_selecionados(hwnd_listview):
    indices = []
    indice = -1

    while True:
        indice = win32gui.SendMessage(
            hwnd_listview, _LVM_GETNEXTITEM, indice, _LVNI_SELECTED
        )

        if indice == -1:
            break

        indices.append(indice)

    return indices


# Lê o texto (nome exibido) do item indice na listview, que pertence
# a outro processo (explorer.exe) — por isso todo o
# alloc/write/send/read abaixo acontece contra um handle desse
# processo, nunca do nosso próprio.
def _ler_texto_item_remoto(hwnd_listview, indice):
    _, pid = win32process.GetWindowThreadProcessId(hwnd_listview)

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    h_processo = kernel32.OpenProcess(
        _PROCESS_VM_OPERATION
        | _PROCESS_VM_READ
        | _PROCESS_VM_WRITE
        | _PROCESS_QUERY_INFORMATION,
        False,
        pid,
    )

    if not h_processo:
        raise OSError(
            "Não foi possível abrir o processo da Área de Trabalho "
            f"(pid={pid}): {ctypes.WinError()}"
        )

    tamanho_bytes_texto = (
        _TAMANHO_BUFFER_TEXTO * ctypes.sizeof(ctypes.c_wchar)
    )
    tamanho_bytes_struct = ctypes.sizeof(_LVITEMW)
    endereco_texto = None
    endereco_struct = None

    try:
        endereco_texto = kernel32.VirtualAllocEx(
            h_processo,
            None,
            tamanho_bytes_texto,
            _MEM_COMMIT | _MEM_RESERVE,
            _PAGE_READWRITE,
        )
        endereco_struct = kernel32.VirtualAllocEx(
            h_processo,
            None,
            tamanho_bytes_struct,
            _MEM_COMMIT | _MEM_RESERVE,
            _PAGE_READWRITE,
        )

        if not endereco_texto or not endereco_struct:
            raise OSError(f"VirtualAllocEx falhou: {ctypes.WinError()}")

        item = _LVITEMW()
        item.mask = 1  # LVIF_TEXT
        item.iItem = indice
        item.iSubItem = 0
        item.pszText = ctypes.cast(endereco_texto, wintypes.LPWSTR)
        item.cchTextMax = _TAMANHO_BUFFER_TEXTO

        if not kernel32.WriteProcessMemory(
            h_processo,
            endereco_struct,
            ctypes.byref(item),
            tamanho_bytes_struct,
            None,
        ):
            raise OSError(f"WriteProcessMemory falhou: {ctypes.WinError()}")

        user32.SendMessageW(
            hwnd_listview, _LVM_GETITEMTEXTW, indice, endereco_struct
        )

        buffer_local = ctypes.create_unicode_buffer(_TAMANHO_BUFFER_TEXTO)

        if not kernel32.ReadProcessMemory(
            h_processo,
            endereco_texto,
            buffer_local,
            tamanho_bytes_texto,
            None,
        ):
            raise OSError(f"ReadProcessMemory falhou: {ctypes.WinError()}")

        return buffer_local.value

    finally:
        if endereco_texto:
            kernel32.VirtualFreeEx(h_processo, endereco_texto, 0, _MEM_RELEASE)

        if endereco_struct:
            kernel32.VirtualFreeEx(h_processo, endereco_struct, 0, _MEM_RELEASE)

        kernel32.CloseHandle(h_processo)


# Mesma técnica (SHGetKnownFolderPath) já usada e confirmada em
# jarvis/servicos/visao/captura_tela.py — nunca hardcoded, porque a
# Área de Trabalho pode estar redirecionada (ex: sincronização do
# OneDrive).
def _obter_pasta_area_trabalho():
    return Path(
        shell.SHGetKnownFolderPath(
            shellcon.FOLDERID_Desktop,
            0,
            0,
        )
    )


# Resolve o NOME EXIBIDO de um ícone da Área de Trabalho pro caminho
# real do arquivo/pasta/atalho dentro da pasta real da Área de
# Trabalho — nunca aceita ou monta um caminho arbitrário, só resolve
# contra o que já existe de fato ali. Cobre o caso comum de extensão
# oculta (o nome exibido não tem ".txt"/".lnk"), tentando em ordem:
# nome exato, depois nome + qualquer extensão. Se a única
# correspondência for um atalho (.lnk), resolve pro alvo real do
# atalho quando possível — normalmente é isso que o usuário quer
# dizer com "esse arquivo" ao apontar pro ícone.
def _resolver_nome_para_caminho(nome_exibido, pasta_area_trabalho):
    candidato_exato = pasta_area_trabalho / nome_exibido

    if candidato_exato.exists():
        return str(candidato_exato)

    try:
        correspondencias = list(
            pasta_area_trabalho.glob(f"{nome_exibido}.*")
        )
    except OSError:
        correspondencias = []

    if not correspondencias:
        return None

    nao_atalhos = [
        candidato
        for candidato in correspondencias
        if candidato.suffix.lower() != ".lnk"
    ]

    if nao_atalhos:
        return str(nao_atalhos[0])

    caminho_lnk = correspondencias[0]

    try:
        shell_com = win32com.client.Dispatch("WScript.Shell")
        atalho = shell_com.CreateShortCut(str(caminho_lnk))
        alvo = atalho.Targetpath

        if alvo and Path(alvo).exists():
            return alvo

    except Exception:
        pass

    return str(caminho_lnk)


# Retorna (sucesso: bool, resultado), no mesmo formato de
# selecao.obter_arquivo_selecionado(): sucesso=True -> resultado é
# uma lista de caminhos absolutos dos itens selecionados na Área de
# Trabalho; sucesso=False -> resultado é uma mensagem em português
# explicando por que nada foi encontrado. Nunca adivinha.
def obter_item_selecionado_area_trabalho():
    try:
        hwnd_listview = _encontrar_hwnd_listview_area_trabalho()

    except Exception as erro:
        return False, f"Falha ao localizar a Área de Trabalho: {erro}"

    if not hwnd_listview:
        return False, (
            "Não foi possível localizar a listview da Área de "
            "Trabalho."
        )

    indices = _indices_selecionados(hwnd_listview)

    if not indices:
        return False, (
            "Nenhum item selecionado na Área de Trabalho no momento."
        )

    pasta_area_trabalho = _obter_pasta_area_trabalho()
    caminhos = []

    for indice in indices:
        try:
            nome_exibido = _ler_texto_item_remoto(hwnd_listview, indice)

        except Exception as erro:
            return False, (
                "Falha ao ler o item selecionado na Área de "
                f"Trabalho: {erro}"
            )

        caminho = _resolver_nome_para_caminho(
            nome_exibido, pasta_area_trabalho
        )

        if caminho is None:
            return False, (
                f"Não foi possível localizar o arquivo "
                f"'{nome_exibido}' selecionado na Área de Trabalho."
            )

        caminhos.append(caminho)

    return True, caminhos
