from . import detector

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Este pacote não expõe nenhuma tool de voz própria — não faz sentido
# uma tool "ative a ativação por voz" chamável DENTRO de uma sessão
# Gemini já em andamento; o próprio propósito deste pacote é decidir
# quando uma sessão COMEÇA. Por isso obter_function_declarations()
# retorna lista vazia e despachar() nunca reconhece nada — o pacote
# segue o contrato pra ficar consistente com o resto do projeto
# (mesmo caso de explorador_windows), mas iniciar()/pausar()/
# retomar() são chamados diretamente por main_basic.py e por
# GeminiLiveWorker (gemini/live_client_basic.py), nunca via
# despachar(). Por não expor tools, este pacote NÃO entra em
# PACOTES_REGISTRADOS — ver INTEGRATION.md, seção "ativacao_voz".
# ============================================================


def obter_function_declarations():
    return []


def despachar(nome_funcao, argumentos):
    return None


def iniciar(callback_ativacao):
    return detector.iniciar(callback_ativacao)


def pausar():
    detector.pausar()


def retomar():
    detector.retomar()


def esta_ativo():
    return detector.esta_ativo()
