from PySide6.QtCore import QObject, Signal


class SinalizadorInterfacesExtras(QObject):
    solicitou_abrir_configuracoes = Signal()

    solicitou_abrir_chat = Signal()
    solicitou_abrir_envio_arquivo = Signal()

    solicitou_abrir_camera = Signal()
    solicitou_fechar_camera = Signal()

    solicitou_abrir_perfil = Signal()

    solicitou_iniciar_chamada_por_voz = Signal()

    resposta_texto_recebida = Signal(str)


_instancia = None


def obter_sinalizador():
    global _instancia

    if _instancia is None:
        _instancia = SinalizadorInterfacesExtras()

    return _instancia
