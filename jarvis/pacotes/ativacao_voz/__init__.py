from . import detector


def obter_function_declarations():
    return []


def despachar(nome_funcao, argumentos):
    return None


def iniciar(callback_ativacao):
    return detector.iniciar(callback_ativacao)


# Bloqueia até o detector soltar o microfone: nunca os dois ao mesmo tempo.
def pausar():
    detector.pausar()


def retomar():
    detector.retomar()


def esta_ativo():
    return detector.esta_ativo()
