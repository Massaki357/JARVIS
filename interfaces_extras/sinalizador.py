# Sinalizador genérico para pacotes isolados abrirem uma janela Qt
# extra (fora da janela principal) a partir de uma tool_call — que
# roda numa thread de fundo (asyncio.to_thread, dentro do worker do
# Gemini Live), enquanto qualquer janela Qt só pode ser criada/
# mostrada na thread principal.
#
# O padrão: um pacote nunca cria a janela diretamente — ele só emite
# um Signal daqui. A thread principal (ver main_basic.py) conecta
# esse Signal a um slot que efetivamente cria e mostra a janela. Fica
# aqui, em vez de em cada pacote ou em ui/main_window_basic.py, para
# que qualquer pacote novo que precise abrir uma janela só precise
# adicionar um Signal nesta classe — nunca inventar um mecanismo de
# threading próprio.
from PySide6.QtCore import QObject, Signal


class SinalizadorInterfacesExtras(QObject):

    # Emitido por configuracoes/__init__.py quando o usuário pede
    # por voz para abrir a tela de configurações.
    solicitou_abrir_configuracoes = Signal()

    # Emitidos por chat_jarvis/__init__.py quando o usuário pede por
    # voz para abrir a janela de chat ou a janela de envio de
    # arquivo — mesmo padrão de solicitou_abrir_configuracoes acima.
    solicitou_abrir_chat = Signal()
    solicitou_abrir_envio_arquivo = Signal()

    # Diferente dos três sinais acima (que só pedem pra abrir uma
    # janela, sem carregar dado nenhum): este carrega o texto
    # transcrito da resposta falada do Gemini, emitido por
    # GeminiLiveWorker.receber_audio() (gemini/live_client_basic.py)
    # sempre que um turno de resposta termina. Passa pelo
    # sinalizador — em vez de ser um Signal só da instância do
    # worker — de propósito: GeminiLiveWorker é recriado a cada
    # chamada de voz (ver ui/main_window_basic.py), então uma janela
    # de chat aberta antes de uma chamada terminar e outra começar
    # precisaria reconectar a cada troca de instância se o sinal
    # fosse do worker. Conectando nesta instância única e persistente
    # do sinalizador, a janela de chat continua recebendo texto
    # corretamente através de qualquer quantidade de chamadas.
    resposta_texto_recebida = Signal(str)


_instancia = None


# Retorna a instância única (por processo) do sinalizador, criando-a
# na primeira chamada. Criação tardia de propósito: um QObject só
# deve ser instanciado depois que QApplication já existe — importar
# este módulo isoladamente (ex: no import chain de um pacote) nunca
# cria o objeto Qt; só a primeira chamada a esta função cria (ver
# main_basic.py, que chama isso dentro de main(), depois de criar o
# QApplication).
def obter_sinalizador():
    global _instancia

    if _instancia is None:
        _instancia = SinalizadorInterfacesExtras()

    return _instancia
