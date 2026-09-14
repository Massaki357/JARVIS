import sys

from PySide6.QtWidgets import QApplication

from jarvis.nucleo.sinalizador import obter_sinalizador

_janela_configuracoes = None


def _abrir_configuracoes():
    global _janela_configuracoes

    from jarvis.pacotes.configuracoes.window import ConfiguracoesWindow

    _janela_configuracoes = ConfiguracoesWindow()
    _janela_configuracoes.show()


_janela_principal = None

_janela_chat = None


def _obter_worker_ativo():
    if _janela_principal is None:
        return None

    return _janela_principal.live_worker


def _abrir_chat():
    global _janela_chat

    from jarvis.ui.janela_chat import ChatWindow

    _janela_chat = ChatWindow(
        obter_worker_ativo=_obter_worker_ativo,
        ao_fechar=_ao_fechar_chat,
    )
    _janela_chat.show()


def _ao_fechar_chat():
    global _janela_chat
    _janela_chat = None


def _repassar_resposta_texto(texto):
    if _janela_chat is not None:
        _janela_chat.adicionar_resposta_assistente(texto)


_janela_envio_arquivo = None


def _abrir_envio_arquivo():
    global _janela_envio_arquivo

    from jarvis.ui.janela_envio_arquivo import EnvioArquivoWindow

    _janela_envio_arquivo = EnvioArquivoWindow(
        obter_worker_ativo=_obter_worker_ativo,
        ao_fechar=_ao_fechar_envio_arquivo,
    )
    _janela_envio_arquivo.show()


def _ao_fechar_envio_arquivo():
    global _janela_envio_arquivo
    _janela_envio_arquivo = None


_janela_camera = None


def _abrir_camera():
    global _janela_camera

    if _janela_camera is not None:
        _janela_camera.raise_()
        _janela_camera.activateWindow()
        return

    from jarvis.ui.janela_camera import JanelaCamera

    _janela_camera = JanelaCamera(ao_fechar=_ao_fechar_camera)
    _janela_camera.show()


def _fechar_camera():
    if _janela_camera is not None:
        _janela_camera.close()


def _ao_fechar_camera():
    global _janela_camera
    _janela_camera = None


_janela_perfil = None


def _abrir_perfil():
    global _janela_perfil

    if _janela_perfil is not None:
        _janela_perfil.recarregar_perfis()
        _janela_perfil.raise_()
        _janela_perfil.activateWindow()
        return

    from jarvis.ui.janela_perfil import JanelaPerfil

    _janela_perfil = JanelaPerfil(ao_fechar=_ao_fechar_perfil)
    _janela_perfil.show()


def _ao_fechar_perfil():
    global _janela_perfil
    _janela_perfil = None


def _callback_ativacao_detectada():
    obter_sinalizador().solicitou_iniciar_chamada_por_voz.emit()


def _iniciar_chamada_por_voz():
    if _janela_principal is not None:
        _janela_principal.iniciar_chamada_por_voz()


def main():
    global _janela_principal

    app = QApplication(sys.argv)

    # A verificação vem antes dos imports abaixo: eles guardam as chaves de API ao serem importados.
    from jarvis.ui.janela_chaves_api import garantir_chaves_api

    garantir_chaves_api()

    from jarvis.nucleo.preferencias import aplicar_prioridade
    from jarvis.pacotes import ativacao_voz
    from jarvis.pacotes import memoria_obsidian
    from jarvis.ui.janela_principal import MainWindow
    from jarvis.ui.painel_dispositivos import (
        aplicar_preferencias as aplicar_dispositivos,
    )

    aplicar_prioridade()

    memoria_obsidian.iniciar()

    aplicar_dispositivos()

    window = MainWindow()

    _janela_principal = window

    obter_sinalizador().solicitou_abrir_configuracoes.connect(
        _abrir_configuracoes
    )

    obter_sinalizador().solicitou_abrir_chat.connect(
        _abrir_chat
    )
    obter_sinalizador().solicitou_abrir_envio_arquivo.connect(
        _abrir_envio_arquivo
    )

    obter_sinalizador().solicitou_abrir_camera.connect(
        _abrir_camera
    )
    obter_sinalizador().solicitou_fechar_camera.connect(
        _fechar_camera
    )

    obter_sinalizador().solicitou_abrir_perfil.connect(
        _abrir_perfil
    )

    obter_sinalizador().solicitou_iniciar_chamada_por_voz.connect(
        _iniciar_chamada_por_voz
    )

    ativacao_voz.iniciar(
        callback_ativacao=_callback_ativacao_detectada
    )

    obter_sinalizador().resposta_texto_recebida.connect(
        _repassar_resposta_texto
    )

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
