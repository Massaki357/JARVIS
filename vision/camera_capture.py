

# [CURSO] OpenCV (cv2) é responsável por acessar a webcam
# [CURSO] e capturar os frames da câmera.
import cv2

# [CURSO] Pillow (PIL) será utilizada para transformar
# [CURSO] o frame do OpenCV em uma imagem JPEG.
from PIL import Image

# [CURSO] io.BytesIO cria um arquivo totalmente em memória.
# [CURSO] Assim não precisamos salvar nenhuma imagem no disco.
import io

# [CURSO] time fornece funções relacionadas ao tempo.
# [CURSO] Aqui ele é utilizado apenas para aguardar
# [CURSO] alguns milissegundos antes da captura.
import time

# threading.Lock protege o handle compartilhado da câmera (ver seção
# abaixo) contra leituras/aberturas/fechamentos concorrentes vindos
# de threads diferentes (o preview ao vivo roda um QTimer na thread
# principal; capturas pontuais podem vir da thread do worker Gemini).
import threading

# win32comext.shell resolve o caminho REAL de pastas conhecidas do
# Windows (ex: Área de Trabalho) — usado só por salvar_foto_bytes().
# Mesma técnica de vision/screen_capture.py, copiada de forma
# independente aqui (mesma convenção do projeto: cada módulo mantém
# sua própria cópia em vez de importar de outro).
from win32comext.shell import shell, shellcon

# Usados só por salvar_foto_bytes(), pra montar o caminho e o nome
# do arquivo salvo.
from datetime import datetime
from pathlib import Path


# Converte um frame BGR (formato nativo do OpenCV) já capturado em
# bytes JPEG — mesma lógica de conversão/compressão (quality=90) que
# capturar_camera_bytes já usava, extraída aqui pra não duplicar
# entre o caminho de handle compartilhado e o caminho original.
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


# ============================================================
# Handle compartilhado da câmera — usado pelo preview ao vivo
# (ui/camera_window.py, aberto por voz via camera_preview/) e por
# capturar_camera_bytes() abaixo, quando o preview está aberto.
#
# Confirmado ao vivo (não assumido) antes de implementar: a maioria
# das webcams (pelo menos via backend MSMF do OpenCV, usado por
# padrão no Windows) permite abrir um SEGUNDO cv2.VideoCapture(0)
# sem erro imediato, mas isso interfere na leitura do primeiro
# handle enquanto o segundo estiver aberto — um teste real mostrou o
# handle do preview perdendo TODOS os frames durante toda a janela
# em que um segundo handle (simulando capturar_camera_bytes) ficava
# aberto, voltando a funcionar normalmente assim que o segundo era
# liberado. Por isso o preview e as capturas pontuais precisam
# compartilhar o MESMO handle, nunca abrir um cada.
# ============================================================
_lock_camera_compartilhada = threading.Lock()
_camera_compartilhada = None  # cv2.VideoCapture já aberto, ou None


# Abre o handle compartilhado, se ainda não estiver aberto (idempotente
# — chamar de novo com o handle já aberto não faz nada e retorna True).
# Chamada só por ui/camera_window.py ao abrir o preview; o dono do
# ciclo de vida deste handle é a janela de preview, nunca
# capturar_camera_bytes() (que só lê dele quando já está aberto — ver
# abaixo). Retorna False se a câmera não puder ser aberta.
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


# Libera o handle compartilhado, se estiver aberto. Chamada só por
# ui/camera_window.py ao fechar o preview (pelo X ou por voz).
def fechar_camera_compartilhada():
    global _camera_compartilhada

    with _lock_camera_compartilhada:
        if _camera_compartilhada is not None:
            _camera_compartilhada.release()
            _camera_compartilhada = None


def camera_compartilhada_esta_aberta():
    return _camera_compartilhada is not None


# Lê um frame do handle compartilhado, sob lock (protege contra o
# QTimer do preview e uma captura pontual lendo ao mesmo tempo).
# Retorna (sucesso, frame_bgr) — frame_bgr é None se sucesso for
# False, inclusive quando o handle nem está aberto.
def ler_frame_camera_compartilhada():
    with _lock_camera_compartilhada:
        if _camera_compartilhada is None:
            return False, None

        return _camera_compartilhada.read()


# [CURSO] Esta função captura uma fotografia da webcam
# [CURSO] e devolve a imagem em formato JPEG (bytes).
# [CURSO] Os bytes serão enviados diretamente ao Gemini.
def capturar_camera_bytes():
    """
    Captura uma imagem da webcam padrão.
    Descarta alguns frames iniciais para dar tempo
    da câmera ajustar foco, luz e exposição.
    """

    # Se o preview ao vivo estiver aberto, reaproveita o MESMO handle
    # já aberto por ele em vez de abrir um segundo — evita o conflito
    # de dispositivo confirmado ao vivo (ver bloco acima). Como o
    # handle compartilhado já está aberto e estabilizado há um
    # tempo, não precisa do sleep de aquecimento nem de descartar
    # vários frames — um único read já é um frame atual.
    if camera_compartilhada_esta_aberta():
        sucesso, frame = ler_frame_camera_compartilhada()

        if not sucesso:
            raise RuntimeError(
                "Não foi possível capturar imagem da webcam "
                "(preview ao vivo aberto)."
            )

        return _frame_para_jpeg_bytes(frame)

    # Comportamento original, inalterado, pro caso em que não há
    # preview aberto — abre e fecha seu próprio handle, como sempre.

    # [CURSO] Abre a webcam padrão do computador.
    # [CURSO] O índice 0 normalmente representa
    # [CURSO] a primeira câmera disponível.
    camera = cv2.VideoCapture(0)

    # [CURSO] Confirma se a câmera foi aberta corretamente.
    # [CURSO] Caso contrário interrompe a execução.
    if not camera.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam.")

    # Dá um pequeno tempo para a câmera estabilizar
    # [CURSO] Muitas webcams precisam de alguns instantes
    # [CURSO] para ajustar foco, brilho e exposição.
    time.sleep(0.8)

    # [CURSO] Variável que armazenará o último frame válido.
    frame = None

    # Descarta os primeiros frames ruins/desatualizados
    # [CURSO] Os primeiros frames normalmente possuem
    # [CURSO] baixa qualidade ou pertencem ao buffer antigo.
    # [CURSO] Por isso capturamos alguns antes da imagem final.
    for _ in range(10):

        # [CURSO] Lê um frame da câmera.
        # [CURSO] sucesso indica se a captura ocorreu corretamente.
        sucesso, frame = camera.read()

        # [CURSO] Em caso de erro, libera imediatamente
        # [CURSO] a webcam antes de interromper a função.
        if not sucesso:
            camera.release()
            raise RuntimeError("Não foi possível capturar imagem da webcam.")

    # [CURSO] Libera a webcam para que outros programas
    # [CURSO] possam utilizá-la normalmente.
    camera.release()

    return _frame_para_jpeg_bytes(frame)


# Resolve o caminho REAL da Área de Trabalho do usuário atual — mesma
# lógica de vision/screen_capture.py._obter_pasta_area_trabalho,
# copiada aqui de forma independente (nunca hardcoded como
# C:\Users\<nome>\Desktop, porque pode estar redirecionada pelo
# OneDrive).
def _obter_pasta_area_trabalho():
    return Path(
        shell.SHGetKnownFolderPath(
            shellcon.FOLDERID_Desktop,
            0,
            0,
        )
    )


# Evita sobrescrever uma foto anterior salva no mesmo segundo — mesma
# lógica de vision/screen_capture.py._caminho_sem_sobrescrever,
# independentemente copiada aqui.
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


# Salva bytes JPEG já capturados por capturar_camera_bytes() num
# arquivo, dentro de <Área de Trabalho>\JarvisRecebidos — mesma pasta
# e mesmo esquema de nome (com timestamp) de
# screen_capture.salvar_print_bytes, só trocando o prefixo pra
# "foto_" em vez de "print_", pra diferenciar as duas origens na
# mesma pasta. Retorna o caminho completo do arquivo salvo.
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