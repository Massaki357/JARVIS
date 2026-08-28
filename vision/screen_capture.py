

# [CURSO] io permite criar arquivos temporários diretamente na memória RAM.
# [CURSO] Isso evita salvar imagens no disco antes de enviá-las ao Gemini.
import io

# [CURSO] mss é uma biblioteca extremamente rápida para captura de tela.
# [CURSO] Ela acessa diretamente os pixels do monitor.
import mss

# [CURSO] Pillow (PIL) será utilizada para transformar os pixels
# [CURSO] capturados pelo mss em uma imagem JPEG.
from PIL import Image


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