import ctypes

import ctypes.wintypes

import time


_USER32 = ctypes.windll.user32


MOUSEEVENTF_LEFTDOWN = 0x0002

MOUSEEVENTF_LEFTUP = 0x0004

MOUSEEVENTF_RIGHTDOWN = 0x0008

MOUSEEVENTF_RIGHTUP = 0x0010

MOUSEEVENTF_WHEEL = 0x0800

WHEEL_DELTA = 120


try:
    _USER32.SetProcessDPIAware()
except Exception:
    pass


def _limitar_quantidade(quantidade):
    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        quantidade = 3

    return max(1, min(10, quantidade))


def _evento_mouse(flags, dados=0):
    _USER32.mouse_event(
        flags,
        0,
        0,
        dados,
        0,
    )


def rolar_pagina(direcao, quantidade=3):
    direcao = str(direcao).strip().lower()

    quantidade = _limitar_quantidade(quantidade)

    if direcao in ("cima", "para cima", "subir"):
        _evento_mouse(
            MOUSEEVENTF_WHEEL,
            WHEEL_DELTA * quantidade,
        )
        return f"Rolei a página para cima em {quantidade} passos."

    if direcao in ("baixo", "para baixo", "descer"):
        _evento_mouse(
            MOUSEEVENTF_WHEEL,
            -WHEEL_DELTA * quantidade,
        )
        return f"Rolei a página para baixo em {quantidade} passos."

    return "Direção inválida. Use cima ou baixo."


def clicar_mouse():
    _evento_mouse(MOUSEEVENTF_LEFTDOWN)

    _evento_mouse(MOUSEEVENTF_LEFTUP)

    return "Clique executado na posição atual do mouse."


def duplo_clique_mouse():
    clicar_mouse()

    time.sleep(0.12)

    clicar_mouse()

    return "Clique duplo executado na posição atual do mouse."


def clique_direito_mouse():
    _evento_mouse(MOUSEEVENTF_RIGHTDOWN)
    _evento_mouse(MOUSEEVENTF_RIGHTUP)

    return "Clique com o botão direito executado na posição atual do mouse."


# Nunca vira tool de voz: só clique_visual chama, depois do localizador aprovar.
def mover_e_clicar(x, y, duracao=0.35):
    try:
        x = int(x)
        y = int(y)
        duracao = float(duracao)

    except (TypeError, ValueError):
        return "Coordenadas inválidas. Nenhum clique foi executado."

    largura = _USER32.GetSystemMetrics(0)
    altura = _USER32.GetSystemMetrics(1)

    if not (0 <= x < largura and 0 <= y < altura):
        return "Coordenadas fora da tela. Nenhum clique foi executado."

    ponto = ctypes.wintypes.POINT()

    _USER32.GetCursorPos(ctypes.byref(ponto))

    inicio_x = ponto.x
    inicio_y = ponto.y

    passos = max(1, int(max(0.05, min(1.0, duracao)) * 60))

    for passo in range(1, passos + 1):
        proporcao = passo / passos

        atual_x = round(
            inicio_x + (x - inicio_x) * proporcao
        )

        atual_y = round(
            inicio_y + (y - inicio_y) * proporcao
        )

        _USER32.SetCursorPos(atual_x, atual_y)

        time.sleep(max(0.001, duracao / passos))

    clicar_mouse()

    return f"Clique visual executado em x={x}, y={y}."
