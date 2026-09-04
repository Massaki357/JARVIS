# Janela de preview ao vivo da webcam — fora de qualquer arquivo
# do curso. Diferente de analisar_camera/tirar_foto_camera (um único
# frame), mostra o vídeo continuamente, atualizado por um QTimer.
#
# Usa o handle COMPARTILHADO da câmera (jarvis/servicos/visao/captura_camera.py) em
# vez de abrir o seu próprio — é esta janela que abre e fecha o
# handle compartilhado (dono do ciclo de vida dele), e
# capturar_camera_bytes() só lê dele quando já está aberto. Ver o
# comentário no topo de jarvis/servicos/visao/captura_camera.py pro porquê disso —
# confirmado ao vivo que duas aberturas simultâneas da câmera
# interferem uma na outra.
import cv2

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.servicos.visao.captura_camera import (
    abrir_camera_compartilhada,
    fechar_camera_compartilhada,
    ler_frame_camera_compartilhada,
)

# Identidade visual compartilhada com o resto do app (ver
# jarvis/ui/estilo.py) — esta janela é top-level, separada de
# MainWindow, então precisa aplicar o estilo nela mesma.
from jarvis.ui.estilo import ESTILO_GLOBAL

# Intervalo entre atualizações do preview, em milissegundos.
# ~33ms ≈ 30fps — ajustável se ficar pesado demais na prática.
INTERVALO_ATUALIZACAO_MS = 33


class JanelaCamera(QWidget):

    def __init__(self, ao_fechar=None):
        super().__init__()

        # Chamado quando a janela fecha (pelo X ou por voz, via
        # closeEvent abaixo) — mesmo padrão de ChatWindow/
        # EnvioArquivoWindow, pra quem criou a janela (main.py)
        # saber que ela não existe mais e limpar sua referência.
        self._ao_fechar = ao_fechar

        self.setWindowTitle("Câmera ao vivo - jarvis")
        self.resize(640, 480)
        self.setStyleSheet(ESTILO_GLOBAL)

        self._label_feed = QLabel("Iniciando a câmera...")
        self._label_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label_feed)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._atualizar_frame)

        if abrir_camera_compartilhada():
            self._timer.start(INTERVALO_ATUALIZACAO_MS)
        else:
            self._label_feed.setText(
                "Não foi possível acessar a webcam."
            )

    def _atualizar_frame(self):
        sucesso, frame_bgr = ler_frame_camera_compartilhada()

        if not sucesso or frame_bgr is None:
            return

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        altura, largura, _canais = frame_rgb.shape

        imagem_qt = QImage(
            frame_rgb.data,
            largura,
            altura,
            frame_rgb.strides[0],
            QImage.Format.Format_RGB888,
        )

        # QPixmap.fromImage copia os dados de pixel internamente, por
        # isso é seguro o array numpy (frame_rgb) sair de escopo logo
        # depois — o QPixmap resultante não depende mais dele.
        self._label_feed.setPixmap(QPixmap.fromImage(imagem_qt))

    def closeEvent(self, event):
        self._timer.stop()

        # Libera o handle compartilhado da câmera — sem isso, o
        # dispositivo ficaria preso mesmo depois da janela fechar.
        fechar_camera_compartilhada()

        if self._ao_fechar:
            self._ao_fechar()

        super().closeEvent(event)
