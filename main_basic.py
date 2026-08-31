
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
from ui.main_window_basic import MainWindow

# Sinalizador genérico usado por pacotes isolados que precisam abrir
# uma janela Qt extra a partir de uma tool_call (thread de fundo) —
# ver interfaces_extras/sinalizador.py. A conexão do sinal ao slot
# que efetivamente cria a janela fica aqui, e não em
# ui/main_window_basic.py, de propósito — ver INTEGRATION.md, seção
# "Tela de configurações".
from interfaces_extras.sinalizador import obter_sinalizador

# Referência mantida viva no módulo — sem isso, o Qt destruiria a
# janela assim que _abrir_configuracoes() retornasse (nenhuma outra
# variável ficaria segurando o objeto).
_janela_configuracoes = None


def _abrir_configuracoes():
    global _janela_configuracoes

    from configuracoes.window import ConfiguracoesWindow

    _janela_configuracoes = ConfiguracoesWindow()
    _janela_configuracoes.show()


# Referência à MainWindow, guardada só pra chat_jarvis (chat e envio
# de arquivo) conseguir ler window.live_worker sem precisar editar
# ui/main_window_basic.py — MainWindow já expõe esse atributo
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

    from ui.chat_window import ChatWindow

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

    from ui.envio_arquivo_window import EnvioArquivoWindow

    _janela_envio_arquivo = EnvioArquivoWindow(
        obter_worker_ativo=_obter_worker_ativo,
        ao_fechar=_ao_fechar_envio_arquivo,
    )
    _janela_envio_arquivo.show()


def _ao_fechar_envio_arquivo():
    global _janela_envio_arquivo
    _janela_envio_arquivo = None


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
    # uma thread de fundo, dentro de configuracoes/__init__.py) ao
    # slot que cria a janela — só pode acontecer na thread principal.
    obter_sinalizador().solicitou_abrir_configuracoes.connect(
        _abrir_configuracoes
    )

    # Mesmo padrão, pras janelas de chat e envio de arquivo (emitidas
    # de uma thread de fundo, dentro de chat_jarvis/__init__.py).
    obter_sinalizador().solicitou_abrir_chat.connect(
        _abrir_chat
    )
    obter_sinalizador().solicitou_abrir_envio_arquivo.connect(
        _abrir_envio_arquivo
    )

    # Entrega a transcrição de cada resposta falada do Gemini pra
    # janela de chat, se ela estiver aberta — emitido de dentro do
    # loop assíncrono do worker (thread de fundo), ver
    # GeminiLiveWorker.receber_audio em gemini/live_client_basic.py.
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