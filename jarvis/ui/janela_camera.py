import cv2

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.servicos.visao.captura_camera import (
    abrir_camera_compartilhada,
    fechar_camera_compartilhada,
    ler_frame_camera_compartilhada,
)

from jarvis.ui.estilo import ESTILO_GLOBAL

INTERVALO_ATUALIZACAO_MS = 33


class JanelaCamera(QWidget):
    def __init__(self, ao_fechar=None):
        super().__init__()

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

        self._label_feed.setPixmap(QPixmap.fromImage(imagem_qt))

    def closeEvent(self, event):
        self._timer.stop()

        fechar_camera_compartilhada()

        if self._ao_fechar:
            self._ao_fechar()

        super().closeEvent(event)
