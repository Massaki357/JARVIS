from . import selecao

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Este pacote não expõe nenhuma tool de voz própria — não faz
# sentido o usuário pedir "descubra o arquivo selecionado" como um
# fim em si; é sempre um passo interno de outra tool (enviar_email
# com usar_arquivo_selecionado=true). Por isso
# obter_function_declarations() retorna lista vazia e despachar()
# nunca reconhece nada — o pacote segue o contrato pra ficar
# consistente com o resto do projeto, mas obter_arquivo_selecionado()
# é chamado diretamente pelo cliente (jarvis/gemini/cliente_live.py),
# igual capturar_camera_bytes() já é. Justamente por não expor tools,
# este pacote NÃO precisa entrar em PACOTES_REGISTRADOS — ver
# docs/INTEGRATION.md, seção "explorador_windows".
# ============================================================


def obter_function_declarations():
    return []


def despachar(nome_funcao, argumentos):
    return None


def obter_arquivo_selecionado():
    return selecao.obter_arquivo_selecionado()
