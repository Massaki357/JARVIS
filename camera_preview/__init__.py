# Usado só para montar as FunctionDeclarations deste pacote — mesmo
# padrão de rede_jarvis/casa_inteligente/delegacao_ia/admin_terminal
# (ver INTEGRATION.md).
from google.genai import types

from interfaces_extras.sinalizador import obter_sinalizador

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar(). Aqui,
# despachar() só EMITE um sinal — a janela em si só pode ser criada
# na thread principal do Qt, nunca na thread de fundo onde
# despachar() é chamado — mesmo padrão de configuracoes/ e
# chat_jarvis/ (ver interfaces_extras/sinalizador.py e main_basic.py
# para o porquê e onde a janela é de fato criada/fechada).
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_camera",
        description=(
            "Abre uma janela mostrando o vídeo AO VIVO da webcam, "
            "atualizado continuamente — diferente de analisar_camera "
            "(descreve um único frame, sem abrir janela nenhuma) e "
            "tirar_foto_camera (salva um único frame). Use somente "
            "quando o usuário pedir explicitamente para abrir, "
            "mostrar ou ver a câmera ao vivo, num preview contínuo "
            "(ex: 'abra minha câmera', 'mostra o vídeo da webcam', "
            "'quero ver a câmera ao vivo'). Se a janela já estiver "
            "aberta, não abre outra — apenas foca a existente. Nunca "
            "use espontaneamente."
        ),
    ),
    types.FunctionDeclaration(
        name="fechar_camera",
        description=(
            "Fecha a janela de vídeo ao vivo da webcam aberta por "
            "abrir_camera, liberando o dispositivo. Use somente "
            "quando o usuário pedir explicitamente para fechar a "
            "câmera ou parar de ver o vídeo ao vivo (ex: 'feche a "
            "câmera', 'pode fechar o vídeo da webcam'). Se a janela "
            "não estiver aberta, não há nada a fazer. Nunca use "
            "espontaneamente."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    if nome_funcao == "abrir_camera":
        return abrir_camera()

    if nome_funcao == "fechar_camera":
        return fechar_camera()

    return None


def abrir_camera():
    obter_sinalizador().solicitou_abrir_camera.emit()

    return "Abrindo o vídeo ao vivo da câmera."


def fechar_camera():
    obter_sinalizador().solicitou_fechar_camera.emit()

    return "Fechando o vídeo da câmera."
