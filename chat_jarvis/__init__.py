# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver INTEGRATION.md).
from google.genai import types

from interfaces_extras.sinalizador import obter_sinalizador

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar(). Aqui,
# despachar() só EMITE um sinal — nenhuma das duas janelas pode ser
# criada na thread de fundo onde despachar() é chamado. Mesmo padrão
# já usado por configuracoes/__init__.py (ver
# interfaces_extras/sinalizador.py e main_basic.py).
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_chat",
        description=(
            "Abre uma janela de chat de texto conectada a esta "
            "mesma conversa por voz, onde o usuário pode digitar "
            "mensagens ou arrastar um arquivo como contexto "
            "adicional — tudo isso conta na mesma conversa, não é "
            "um chat separado. Use somente quando o usuário pedir "
            "explicitamente para abrir o chat, a janela de texto, "
            "ou algo parecido (ex: 'abre o chat', 'quero digitar', "
            "'abre uma janela de texto pra eu escrever'). Nunca use "
            "espontaneamente."
        ),
    ),
    types.FunctionDeclaration(
        name="abrir_envio_arquivo",
        description=(
            "Abre uma janela pra o usuário enviar um arquivo "
            "(imagem, PDF ou texto) como contexto adicional pra "
            "esta mesma conversa por voz, arrastando o arquivo ou "
            "selecionando pelo diálogo do sistema. Use somente "
            "quando o usuário pedir explicitamente para mandar, "
            "enviar ou compartilhar um arquivo com você (ex: 'eu "
            "quero te mandar um arquivo', 'deixa eu te enviar "
            "isso aqui'). Nunca use espontaneamente."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    if nome_funcao == "abrir_chat":
        return abrir_chat()

    if nome_funcao == "abrir_envio_arquivo":
        return abrir_envio_arquivo()

    return None


def abrir_chat():
    obter_sinalizador().solicitou_abrir_chat.emit()

    return "Abrindo a janela de chat."


def abrir_envio_arquivo():
    obter_sinalizador().solicitou_abrir_envio_arquivo.emit()

    return "Abrindo a janela de envio de arquivo."
