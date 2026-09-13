import io

import mss

from PIL import Image

import win32api

from win32comext.shell import shell, shellcon

from datetime import datetime
from pathlib import Path


def capturar_tela_bytes():
    with mss.mss() as sct:
        monitor = sct.monitors[1]

        screenshot = sct.grab(
            monitor
        )

        imagem = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        buffer = io.BytesIO()

        imagem.save(
            buffer,
            format="JPEG",
            quality=80
        )

        return buffer.getvalue()


def _screenshot_para_jpeg_bytes(screenshot):
    imagem = Image.frombytes(
        "RGB",
        screenshot.size,
        screenshot.rgb,
    )

    buffer = io.BytesIO()

    imagem.save(
        buffer,
        format="JPEG",
        quality=80,
    )

    return buffer.getvalue()


def capturar_monitor_do_cursor_bytes():
    with mss.mss() as sct:
        monitores = sct.monitors[1:]

        cursor_x, cursor_y = win32api.GetCursorPos()

        monitor_do_cursor = None

        for monitor in monitores:
            dentro_da_largura = (
                monitor["left"]
                <= cursor_x
                < monitor["left"] + monitor["width"]
            )

            dentro_da_altura = (
                monitor["top"]
                <= cursor_y
                < monitor["top"] + monitor["height"]
            )

            if dentro_da_largura and dentro_da_altura:
                monitor_do_cursor = monitor
                break

        if monitor_do_cursor is None:
            monitor_do_cursor = sct.monitors[1]

        screenshot = sct.grab(monitor_do_cursor)

        return _screenshot_para_jpeg_bytes(screenshot)


def _obter_pasta_area_trabalho():
    return Path(
        shell.SHGetKnownFolderPath(
            shellcon.FOLDERID_Desktop,
            0,
            0,
        )
    )


def _caminho_sem_sobrescrever(caminho):
    if not caminho.exists():
        return caminho

    contador = 1

    while True:
        candidato = caminho.with_stem(
            f"{caminho.stem}_{contador}"
        )

        if not candidato.exists():
            return candidato

        contador += 1


def salvar_print_bytes(imagem_bytes):
    pasta_destino = _obter_pasta_area_trabalho() / "JarvisRecebidos"

    pasta_destino.mkdir(
        parents=True,
        exist_ok=True,
    )

    nome_arquivo = (
        "print_"
        + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        + ".jpg"
    )

    caminho_arquivo = _caminho_sem_sobrescrever(
        pasta_destino / nome_arquivo
    )

    caminho_arquivo.write_bytes(imagem_bytes)

    return str(caminho_arquivo)
