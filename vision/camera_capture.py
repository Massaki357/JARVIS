

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


# [CURSO] Esta função captura uma fotografia da webcam
# [CURSO] e devolve a imagem em formato JPEG (bytes).
# [CURSO] Os bytes serão enviados diretamente ao Gemini.
def capturar_camera_bytes():
    """
    Captura uma imagem da webcam padrão.
    Descarta alguns frames iniciais para dar tempo
    da câmera ajustar foco, luz e exposição.
    """

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
    time.sleep(0.5)

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

    # [CURSO] O OpenCV trabalha em BGR.
    # [CURSO] A Pillow utiliza RGB.
    # [CURSO] Portanto fazemos a conversão das cores.
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # [CURSO] Converte o array NumPy em uma imagem Pillow.
    imagem = Image.fromarray(frame_rgb)

    # [CURSO] Cria um arquivo temporário somente na memória RAM.
    buffer = io.BytesIO()

    # [CURSO] Salva a imagem no buffer em formato JPEG.
    # [CURSO] quality=90 oferece ótima qualidade
    # [CURSO] mantendo um tamanho relativamente pequeno.
    imagem.save(
        buffer,
        format="JPEG",
        quality=90
    )

    # [CURSO] Retorna apenas os bytes do JPEG.
    # [CURSO] Esses bytes podem ser enviados diretamente
    # [CURSO] para a IA sem criar arquivos no disco.
    return buffer.getvalue()