import cv2

from PIL import Image

import io

import time

import threading

from win32comext.shell import shell, shellcon

from datetime import datetime
from pathlib import Path


def _frame_para_jpeg_bytes(frame_bgr):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    imagem = Image.fromarray(frame_rgb)

    buffer = io.BytesIO()

    imagem.save(
        buffer,
        format="JPEG",
        quality=90,
    )

    return buffer.getvalue()


_lock_camera_compartilhada = threading.Lock()
_camera_compartilhada = None


def abrir_camera_compartilhada():
    global _camera_compartilhada

    with _lock_camera_compartilhada:
        if _camera_compartilhada is not None:
            return True

        camera = cv2.VideoCapture(0)

        if not camera.isOpened():
            return False

        _camera_compartilhada = camera
        return True


def fechar_camera_compartilhada():
    global _camera_compartilhada

    with _lock_camera_compartilhada:
        if _camera_compartilhada is not None:
            _camera_compartilhada.release()
            _camera_compartilhada = None


# Consumidores novos checam isto antes de abrir VideoCapture(0).
def camera_compartilhada_esta_aberta():
    return _camera_compartilhada is not None


def ler_frame_camera_compartilhada():
    with _lock_camera_compartilhada:
        if _camera_compartilhada is None:
            return False, None

        return _camera_compartilhada.read()


def capturar_camera_bytes():
    if camera_compartilhada_esta_aberta():
        sucesso, frame = ler_frame_camera_compartilhada()

        if not sucesso:
            raise RuntimeError(
                "Não foi possível capturar imagem da webcam "
                "(preview ao vivo aberto)."
            )

        return _frame_para_jpeg_bytes(frame)

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam.")

    time.sleep(0.8)

    frame = None

    for _ in range(10):
        sucesso, frame = camera.read()

        if not sucesso:
            camera.release()
            raise RuntimeError("Não foi possível capturar imagem da webcam.")

    camera.release()

    return _frame_para_jpeg_bytes(frame)


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


def salvar_foto_bytes(imagem_bytes):
    pasta_destino = _obter_pasta_area_trabalho() / "JarvisRecebidos"

    pasta_destino.mkdir(
        parents=True,
        exist_ok=True,
    )

    nome_arquivo = (
        "foto_"
        + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        + ".jpg"
    )

    caminho_arquivo = _caminho_sem_sobrescrever(
        pasta_destino / nome_arquivo
    )

    caminho_arquivo.write_bytes(imagem_bytes)

    return str(caminho_arquivo)
