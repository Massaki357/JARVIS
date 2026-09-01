
# Ativar o ambiente virtual:
# .\venv\Scripts\Activate.ps1

# [CURSO] sys fornece acesso aos argumentos da linha de comando
# [CURSO] e também é utilizado para encerrar corretamente a aplicação.
import sys

# [CURSO] QApplication é o núcleo de qualquer aplicação Qt.
# [CURSO] Ela cria o loop principal responsável pela interface gráfica.
from PySide6.QtWidgets import QApplication

# [CURSO] Importa a janela principal da versão básica do ALFRED.
# [CURSO] Toda a interface será criada por essa classe.
from jarvis.ui.janela_principal import MainWindow

# Sinalizador genérico usado por pacotes isolados que precisam abrir
# uma janela Qt extra a partir de uma tool_call (thread de fundo) —
# ver jarvis/nucleo/sinalizador.py. A conexão do sinal ao slot
# que efetivamente cria a janela fica aqui, e não em
# jarvis/ui/janela_principal.py, de propósito — ver docs/INTEGRATION.md, seção
# "Tela de configurações".
from jarvis.nucleo.sinalizador import obter_sinalizador

# Pacote isolado com a ativação por voz (palavra-chave) — ver
# jarvis/pacotes/ativacao_voz/detector.py. iniciar() é chamado uma única vez aqui,
# depois que a janela principal existe; pausar()/retomar() (chamados
# por GeminiLiveWorker a cada chamada, pra nunca haver dois handles
# de microfone concorrentes) não são responsabilidade deste arquivo.
from jarvis.pacotes import ativacao_voz

# Referência mantida viva no módulo — sem isso, o Qt destruiria a
# janela assim que _abrir_configuracoes() retornasse (nenhuma outra
# variável ficaria segurando o objeto).
_janela_configuracoes = None


def _abrir_configuracoes():
    global _janela_configuracoes

    from jarvis.pacotes.configuracoes.window import ConfiguracoesWindow

    _janela_configuracoes = ConfiguracoesWindow()
    _janela_configuracoes.show()


# Referência à MainWindow, guardada só pra chat_jarvis (chat e envio
# de arquivo) conseguir ler window.live_worker sem precisar editar
# jarvis/ui/janela_principal.py — MainWindow já expõe esse atributo
# publicamente, isso aqui só guarda uma referência à própria janela
# principal criada em main().
_janela_principal = None

# Referência à janela de chat aberta agora, se houver — usada tanto
# pra manter o objeto vivo quanto pra _repassar_resposta_texto saber
# se existe uma janela de chat pra entregar o texto.
_janela_chat = None


# Lida sempre que uma mensagem/arquivo precisa ser enviado pra
# sessão Live — nunca uma referência fixa, porque GeminiLiveWorker é
# recriado a cada chamada de voz (self.live_worker é None entre
# chamadas). Passado como callback pras janelas de chat/envio de
# arquivo, que chamam isso de novo a cada envio.
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


# Entrega o texto transcrito de uma resposta do Gemini pra janela de
# chat, se ela estiver aberta agora. Se não estiver, o texto é
# apenas descartado — não há nada esperando por ele.
def _repassar_resposta_texto(texto):
    if _janela_chat is not None:
        _janela_chat.adicionar_resposta_assistente(texto)


# Referência à janela de envio de arquivo aberta agora, se houver.
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


# Referência à janela de vídeo ao vivo da câmera aberta agora, se
# houver — usada tanto pra manter o objeto vivo quanto pra
# _abrir_camera saber se já existe uma janela pra só focar em vez de
# abrir outra, e pra _fechar_camera saber se há algo a fechar.
_janela_camera = None


def _abrir_camera():
    global _janela_camera

    # Se já estiver aberta, não abre uma segunda — só foca a
    # existente (traz pra frente e dá foco).
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


# Chamado numa thread de fundo própria de jarvis/pacotes/ativacao_voz/detector.py,
# assim que a palavra-chave de ativação é reconhecida — nunca a
# thread da GUI, por isso só faz uma coisa thread-safe (emitir um
# Signal do sinalizador), nunca chama um método de widget diretamente
# a partir daqui.
def _callback_ativacao_detectada():
    obter_sinalizador().solicitou_iniciar_chamada_por_voz.emit()


# Roda na thread principal (slot conectado ao Signal acima) — dispara
# a MESMA ação do clique no botão de iniciar chamada, reaproveitada,
# não duplicada.
def _iniciar_chamada_por_voz():
    if _janela_principal is not None:
        _janela_principal.alternar_chamada()


# [CURSO] Função principal da aplicação.
# [CURSO] Ela inicializa o Qt, cria a janela e inicia o loop de eventos.
def main():
    global _janela_principal

    # [CURSO] Cria a aplicação Qt.
    # [CURSO] sys.argv permite que o Qt receba argumentos
    # [CURSO] passados pela linha de comando, quando existirem.
    app = QApplication(sys.argv)

    # [CURSO] Cria uma instância da janela principal.
    window = MainWindow()

    # Guardada pra _obter_worker_ativo conseguir ler
    # window.live_worker (ver comentário na definição da função).
    _janela_principal = window

    # Conecta o pedido de abrir a tela de configurações (emitido de
    # uma thread de fundo, dentro de jarvis/pacotes/configuracoes/__init__.py) ao
    # slot que cria a janela — só pode acontecer na thread principal.
    obter_sinalizador().solicitou_abrir_configuracoes.connect(
        _abrir_configuracoes
    )

    # Mesmo padrão, pras janelas de chat e envio de arquivo (emitidas
    # de uma thread de fundo, dentro de jarvis/pacotes/chat_jarvis/__init__.py).
    obter_sinalizador().solicitou_abrir_chat.connect(
        _abrir_chat
    )
    obter_sinalizador().solicitou_abrir_envio_arquivo.connect(
        _abrir_envio_arquivo
    )

    # Mesmo padrão, pra janela de vídeo ao vivo da câmera (emitidos
    # de uma thread de fundo, dentro de jarvis/pacotes/camera_preview/__init__.py).
    obter_sinalizador().solicitou_abrir_camera.connect(
        _abrir_camera
    )
    obter_sinalizador().solicitou_fechar_camera.connect(
        _fechar_camera
    )

    # Mesmo padrão, pro pedido de iniciar uma chamada por ativação de
    # voz (emitido de uma thread de fundo própria, dentro de
    # jarvis/pacotes/ativacao_voz/detector.py).
    obter_sinalizador().solicitou_iniciar_chamada_por_voz.connect(
        _iniciar_chamada_por_voz
    )

    # Começa a escutar a palavra-chave de ativação agora — só depois
    # da janela principal existir, já que o callback (disparado numa
    # thread de fundo) precisa de _janela_principal pronta pra
    # funcionar. Se o modelo de reconhecimento de voz (Vosk) não
    # puder ser carregado, ou o microfone não puder ser aberto (ver
    # jarvis/pacotes/ativacao_voz/detector.py), fica indisponível silenciosamente
    # (só um aviso no console) — o botão manual continua funcionando
    # normalmente de qualquer forma.
    ativacao_voz.iniciar(
        callback_ativacao=_callback_ativacao_detectada
    )

    # Entrega a transcrição de cada resposta falada do Gemini pra
    # janela de chat, se ela estiver aberta — emitido de dentro do
    # loop assíncrono do worker (thread de fundo), ver
    # GeminiLiveWorker.receber_audio em jarvis/gemini/cliente_live.py.
    obter_sinalizador().resposta_texto_recebida.connect(
        _repassar_resposta_texto
    )

    # [CURSO] Torna a janela visível para o usuário.
    window.show()

    # [CURSO] Inicia o loop de eventos do Qt.
    # [CURSO] A aplicação permanecerá aberta até que a janela seja fechada.
    # [CURSO] sys.exit garante que o código de encerramento
    # [CURSO] seja devolvido corretamente ao sistema operacional.
    sys.exit(app.exec())


# [CURSO] Este bloco garante que a função main()
# [CURSO] seja executada somente quando este arquivo
# [CURSO] for iniciado diretamente.
# [CURSO] Caso ele seja apenas importado por outro módulo,
# [CURSO] a função não será executada automaticamente.
if __name__ == "__main__":
    main()