# Ferramentas NATIVAS disponibilizadas ao cérebro reserva.
#
# Por que este arquivo existe: as tools dos pacotes vêm de graça (o
# esquema.py converte o obter_function_declarations() de cada um), mas
# as nativas — memória, print, foto — são declaradas dentro de
# executar(), em jarvis/gemini/cliente_live.py, como variável local do
# método. Não dá para reaproveitá-las de fora sem reestruturar aquele
# arquivo, que é justamente um dos três temporários do curso que devem
# ser editados o mínimo possível. Então as poucas que fazem sentido no
# modo reserva são declaradas aqui, chamando os MESMOS serviços
# (jarvis/servicos/...), sem reimplementar nenhuma lógica.
#
# O que ficou de fora, de propósito:
#
#   As tools de memoria nao estao aqui: memoria_obsidian e um
#   pacote registrado, entao elas ja sao herdadas automaticamente
#   pela conversao de esquema.py. Declara-las de novo criaria duas
#   ferramentas com o mesmo nome.
#
#   preparar_email / confirmar_envio_email — o envio de email é uma
#   confirmação em duas etapas garantida por CÓDIGO, e o rascunho
#   pendente mora em GeminiLiveWorker.email_pendente. Recriar esse
#   fluxo aqui seria um SEGUNDO caminho capaz de disparar um envio,
#   menos testado que o original — exatamente o que o CLAUDE.md proíbe
#   ("não adicione um caminho novo que chame enviar_email direto sem
#   decidir que isso é intencional"). Se o usuário pedir email no modo
#   reserva, o modelo explica que isso só está disponível na chamada
#   normal.
#
#   analisar_tela / analisar_camera — dependem de mandar a imagem para
#   o modelo dentro da sessão Live, que é justamente o que não existe
#   aqui. Quem quiser análise de imagem no modo reserva tem
#   identificar_planta e consultar_segunda_opiniao_visual, que já vêm
#   pelos pacotes e falam com as próprias APIs.
from jarvis.servicos.visao.captura_camera import (
    capturar_camera_bytes,
    salvar_foto_bytes,
)
from jarvis.servicos.visao.captura_tela import (
    capturar_monitor_do_cursor_bytes,
    salvar_print_bytes,
)

# Nome usado para o pedido de encerrar. Tratado à parte pelo laço do
# modo reserva (ver __init__.py), porque encerrar não é uma ação que
# devolve texto: é o fim da conversa.
NOME_ENCERRAR = "encerrar_chamada"


DECLARACOES = [
    {
        "type": "function",
        "function": {
            "name": "salvar_print_tela",
            "description": (
                "Tira um print da tela onde o cursor do mouse está e "
                "salva em disco. Use quando o usuário pedir para "
                "salvar, guardar ou tirar um print da tela."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tirar_foto_camera",
            "description": (
                "Tira uma foto com a webcam e salva em disco. Use "
                "quando o usuário pedir para tirar, salvar ou "
                "guardar uma foto."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": NOME_ENCERRAR,
            "description": (
                "Encerra a chamada. Use somente quando o usuário "
                "pedir claramente para encerrar, desligar, parar ou "
                "terminar a conversa."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def obter_declaracoes():
    return list(DECLARACOES)


def reconhece(nome):
    return any(
        d["function"]["name"] == nome
        for d in DECLARACOES
    )


# Executa uma ferramenta nativa. Devolve o texto do resultado (que o
# modelo lê antes de responder ao usuário), ou None se o nome não for
# reconhecido — mesma convenção do despachar() dos pacotes.
#
# Nunca levanta exceção: qualquer falha vira um texto explicando o que
# aconteceu, igual todo o resto do projeto.
def despachar(nome, argumentos):
    argumentos = argumentos or {}

    try:
        if nome == "salvar_print_tela":
            caminho = salvar_print_bytes(
                capturar_monitor_do_cursor_bytes()
            )

            return f"Print salvo em {caminho}."

        if nome == "tirar_foto_camera":
            caminho = salvar_foto_bytes(capturar_camera_bytes())

            return f"Foto salva em {caminho}."

    except Exception as erro:
        return (
            f"A função '{nome}' falhou: {erro}. Avise o usuário e "
            "não tente executá-la de novo sozinho."
        )

    return None
