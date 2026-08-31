

# [CURSO] io permite criar arquivos temporários diretamente na memória RAM.
# [CURSO] Isso evita salvar imagens no disco antes de enviá-las ao Gemini.
import io

# [CURSO] mss é uma biblioteca extremamente rápida para captura de tela.
# [CURSO] Ela acessa diretamente os pixels do monitor.
import mss

# [CURSO] Pillow (PIL) será utilizada para transformar os pixels
# [CURSO] capturados pelo mss em uma imagem JPEG.
from PIL import Image

# win32api dá acesso à posição atual do cursor do mouse — usado só
# por capturar_monitor_do_cursor_bytes(), pra descobrir em qual
# monitor o cursor está.
import win32api

# win32comext.shell resolve o caminho REAL de pastas conhecidas do
# Windows (ex: Área de Trabalho) — usado só por salvar_print_bytes().
from win32comext.shell import shell, shellcon

# Usados só por salvar_print_bytes(), pra montar o caminho e o nome
# do arquivo salvo.
from datetime import datetime
from pathlib import Path


# [CURSO] Esta função captura a tela principal do computador
# [CURSO] e devolve uma imagem JPEG em formato de bytes.
# [CURSO] Esses bytes são enviados diretamente para o Gemini Vision.
def capturar_tela_bytes():
    """
    Captura a tela principal
    e retorna JPEG em bytes.
    """

    # [CURSO] Abre o capturador de tela.
    # [CURSO] O bloco "with" garante que os recursos
    # [CURSO] sejam liberados automaticamente ao final.
    with mss.mss() as sct:

        # [CURSO] monitors[1] normalmente representa o monitor principal.
        # [CURSO] monitors[0] corresponde à área virtual de todos os monitores.
        monitor = sct.monitors[1]

        # [CURSO] Captura todos os pixels do monitor escolhido.
        screenshot = sct.grab(
            monitor
        )

        # [CURSO] Converte os pixels capturados em uma imagem Pillow.
        # [CURSO] O mss fornece os pixels em RGB, compatíveis com a Pillow.
        imagem = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        # [CURSO] Cria um buffer em memória para armazenar o JPEG.
        buffer = io.BytesIO()

        # [CURSO] Salva a imagem no buffer.
        # [CURSO] quality=80 reduz o tamanho do arquivo,
        # [CURSO] mantendo boa qualidade para análise pela IA.
        imagem.save(
            buffer,
            format="JPEG",
            quality=80
        )

        # [CURSO] Retorna apenas os bytes da imagem JPEG.
        # [CURSO] Nenhum arquivo é criado no disco.
        return buffer.getvalue()


# Converte uma captura (screenshot) já feita pelo mss em bytes JPEG —
# mesma lógica de conversão/compressão (quality=80) já usada em
# capturar_tela_bytes acima, extraída aqui só pra não duplicar entre
# ela e capturar_monitor_do_cursor_bytes.
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


# Captura o monitor onde o cursor do mouse está agora — em vez do
# monitor principal fixo de capturar_tela_bytes — e devolve JPEG em
# bytes. Usada quando faz mais sentido capturar o monitor que o
# usuário está de fato olhando/mostrando no momento (ex: análise
# pontual de tela e visualização contínua local), não o monitor
# principal do Windows.
def capturar_monitor_do_cursor_bytes():
    with mss.mss() as sct:
        # sct.monitors[0] é a área virtual combinada de todos os
        # monitores — ignorada aqui, queremos só os monitores
        # individuais (índice 1 em diante) pra achar o retângulo
        # exato onde o cursor está.
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
            # O cursor não caiu em nenhum retângulo detectado — raro,
            # mas pode acontecer numa transição entre monitores com
            # resolução/DPI diferentes. Cai no monitor principal (o
            # mesmo usado por capturar_tela_bytes) em vez de travar.
            monitor_do_cursor = sct.monitors[1]

        screenshot = sct.grab(monitor_do_cursor)

        return _screenshot_para_jpeg_bytes(screenshot)


# Resolve o caminho REAL da Área de Trabalho do usuário atual, via a
# API de pastas conhecidas do Windows (SHGetKnownFolderPath) — nunca
# hardcoded como C:\Users\<nome>\Desktop, porque a Área de Trabalho
# pode estar redirecionada (ex: sincronização do OneDrive move a
# pasta pra dentro de C:\Users\<nome>\OneDrive\Área de Trabalho, e
# essa API já resolve isso corretamente). Confirmado ao vivo antes
# de usar, inclusive depois do PySide6 já ter inicializado o COM
# (sem o mesmo problema de conflito do win11toast/WinRT).
def _obter_pasta_area_trabalho():
    return Path(
        shell.SHGetKnownFolderPath(
            shellcon.FOLDERID_Desktop,
            0,
            0,
        )
    )


# Evita sobrescrever um print anterior salvo no mesmo segundo (nome
# de arquivo tem granularidade de segundos) — acrescenta um contador
# se ainda assim colidir.
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


# Salva bytes JPEG já capturados (ex: por capturar_tela_bytes ou
# capturar_monitor_do_cursor_bytes) num arquivo, dentro de
# <Área de Trabalho>\JarvisRecebidos — cria a pasta se não existir.
# Nome do arquivo com timestamp, pra nunca sobrescrever um print
# anterior silenciosamente. Retorna o caminho completo do arquivo
# salvo (string), pro Jarvis poder confirmar por voz onde ficou.
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