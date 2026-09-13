import ctypes
import time
from ctypes import wintypes


_USER32 = ctypes.windll.user32

_KERNEL32 = ctypes.windll.kernel32

_CF_UNICODETEXT = 13

_GMEM_MOVEABLE = 0x0002

_VK_CONTROL = 0x11
_VK_V = 0x56

_KEYEVENTF_KEYUP = 0x0002

_MAXIMO_CARACTERES = 10000


_KERNEL32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_KERNEL32.GlobalAlloc.restype = wintypes.HGLOBAL

_KERNEL32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalLock.restype = wintypes.LPVOID

_KERNEL32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalUnlock.restype = wintypes.BOOL

_KERNEL32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalFree.restype = wintypes.HGLOBAL

_USER32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_USER32.SetClipboardData.restype = wintypes.HANDLE


def _copiar_para_area_transferencia(texto):
    abriu = False

    for _ in range(10):
        if _USER32.OpenClipboard(None):
            abriu = True
            break

        time.sleep(0.05)

    if not abriu:
        raise RuntimeError(
            "Não foi possível acessar a área de transferência do Windows."
        )

    memoria = None
    transferida = False

    try:
        if not _USER32.EmptyClipboard():
            raise RuntimeError(
                "Não foi possível limpar a área de transferência do Windows."
            )

        texto_completo = texto + "\0"

        tamanho = len(texto_completo) * ctypes.sizeof(ctypes.c_wchar)

        memoria = _KERNEL32.GlobalAlloc(
            _GMEM_MOVEABLE,
            tamanho,
        )

        if not memoria:
            raise MemoryError(
                "Não foi possível reservar memória para o texto."
            )

        ponteiro = _KERNEL32.GlobalLock(memoria)

        if not ponteiro:
            raise MemoryError(
                "Não foi possível acessar a memória reservada."
            )

        try:
            ctypes.memmove(
                ponteiro,
                ctypes.create_unicode_buffer(texto_completo),
                tamanho,
            )

        finally:
            _KERNEL32.GlobalUnlock(memoria)

        if not _USER32.SetClipboardData(
            _CF_UNICODETEXT,
            memoria,
        ):
            raise RuntimeError(
                "Não foi possível copiar o texto para a área de transferência."
            )

        transferida = True

    finally:
        _USER32.CloseClipboard()

        if memoria and not transferida:
            _KERNEL32.GlobalFree(memoria)


def _colar_no_campo_ativo():
    _USER32.keybd_event(
        _VK_CONTROL,
        0,
        0,
        0,
    )

    _USER32.keybd_event(
        _VK_V,
        0,
        0,
        0,
    )

    _USER32.keybd_event(
        _VK_V,
        0,
        _KEYEVENTF_KEYUP,
        0,
    )

    _USER32.keybd_event(
        _VK_CONTROL,
        0,
        _KEYEVENTF_KEYUP,
        0,
    )


def escrever_no_campo_ativo(texto):
    texto = str(texto or "")

    if not texto.strip():
        return "Nenhum texto foi informado. Nada foi escrito."

    if len(texto) > _MAXIMO_CARACTERES:
        return (
            "O texto ultrapassa o limite de "
            f"{_MAXIMO_CARACTERES} caracteres. Nada foi escrito."
        )

    try:
        _copiar_para_area_transferencia(texto)

        time.sleep(0.12)

        _colar_no_campo_ativo()

        return "Texto inserido no campo ativo com sucesso."

    except Exception as erro:
        return f"Não foi possível inserir o texto: {erro}"
