# Cérebro reserva: assume a conversa por voz quando a sessão do
# Gemini Live falha, sem que o usuário precise fazer nada.
#
# NÃO é um pacote de tools (obter_function_declarations() devolve
# lista vazia e despachar() sempre devolve None, e ele não entra em
# PACOTES_REGISTRADOS) — mesmo caso de ativacao_voz e
# explorador_windows: não faz sentido uma ferramenta que só pode ser
# chamada DURANTE uma sessão, para um mecanismo cujo propósito é
# funcionar justamente quando essa sessão morreu.
#
# Ele é usado de um jeito só: jarvis/gemini/cliente_live.py chama
# assumir(...) no fim de executar(), quando a chamada terminou por
# falha e não por pedido do usuário.
#
# Como funciona um turno:
#
#   escuta.ouvir()   microfone -> WAV -> Groq Whisper -> texto
#   cerebro.responder()  texto + ferramentas -> Mistral -> texto final
#   fala.falar()     texto -> voz do Windows (SAPI) -> alto-falante
#
# As ferramentas NÃO são reescritas aqui: esquema.py converte as
# FunctionDeclaration que cada pacote já expõe, então tudo que
# funciona na chamada normal continua funcionando no modo reserva, e
# um pacote novo passa a valer nos dois lugares sem tocar neste
# arquivo. Ver docs/INTEGRATION.md, seção "Cérebro reserva".
#
# A escolha de provedor por etapa saiu de medição ao vivo — ver o
# cabeçalho de config.py para os números e o porquê de o cérebro ser
# a Mistral mesmo com a Groq sendo mais rápida.
from . import cerebro, config, escuta, fala


# Contrato padrão dos pacotes, cumprido só para o formato: este
# pacote não expõe nenhuma tool de voz (ver o comentário acima).
def obter_function_declarations():
    return []


def despachar(nome_funcao, argumentos):
    return None


# Diz se o modo reserva tem como funcionar agora. Checado antes de
# assumir para nunca prender o usuário num modo mudo: sem chave de
# transcrição ou de cérebro, é melhor encerrar a chamada como sempre
# foi feito.
def esta_disponivel():
    return bool(config.GROQ_API_KEY and config.MISTRAL_API_KEY)


def motivo_indisponivel():
    faltando = []

    if not config.GROQ_API_KEY:
        faltando.append("GROQ_API_KEY")

    if not config.MISTRAL_API_KEY:
        faltando.append("MISTRAL_API_KEY")

    if not faltando:
        return ""

    return (
        "Modo reserva indisponível: falta "
        + " e ".join(faltando)
        + " no .env."
    )


# Assume a conversa. Roda até deve_continuar() devolver False (o
# usuário encerrou a chamada pela interface ou pela voz, OU — modo
# novo — o Gemini voltou a responder no meio da própria chamada, ver
# jarvis/gemini/cliente_live.py:_conduzir_reserva_temporaria).
#
# Parâmetros:
#   pacotes_registrados  a mesma lista PACOTES_REGISTRADOS do cliente,
#                        recebida por parâmetro para este pacote nunca
#                        importar jarvis/gemini/cliente_live.py (seria
#                        import circular).
#   deve_continuar       callable sem argumentos; False encerra o modo.
#   ao_status            callable(texto) opcional, para a interface.
#   historico_inicial    lista opcional de {"role", "content"} já
#                        existente (ex: transcript da conversa com o
#                        Gemini antes dele ficar mudo) — permite este
#                        pacote assumir NO MEIO de uma conversa já em
#                        andamento, sem perder o contexto. None/omitido
#                        = começa do zero, comportamento de sempre.
#   fila_bloco_externa   queue.Queue opcional repassada pra
#                        escuta.ouvir() — ver o comentário em
#                        escuta.gravar_fala pro porquê (nunca abrir um
#                        segundo stream de microfone concorrente com o
#                        que uma chamada do Gemini ainda ativa já
#                        mantém aberto).
#   ao_turno_concluido   callable(role, texto) opcional, chamado depois
#                        de cada fala do usuário ("user") e cada
#                        resposta falada ("assistant") — permite quem
#                        chamou manter seu próprio transcript da
#                        conversa em dia enquanto este pacote conduz.
#   audio_primeiro_turno bytes WAV opcional — usado SÓ na primeira
#                        escuta do laço (ver escuta.ouvir), pra
#                        aproveitar o áudio que o usuário JÁ tinha
#                        falado, capturado num buffer circular
#                        enquanto ele esperava o Gemini responder, em
#                        vez de esperar ele repetir a pergunta pro
#                        reserva. Turnos seguintes voltam a ouvir ao
#                        vivo normalmente.
#
# Nunca levanta exceção: qualquer falha vira uma volta do laço ou o
# encerramento limpo do modo reserva.
def assumir(
    pacotes_registrados,
    deve_continuar,
    ao_status=None,
    historico_inicial=None,
    fila_bloco_externa=None,
    ao_turno_concluido=None,
    audio_primeiro_turno=None,
):
    def status(texto):
        if ao_status:
            ao_status(texto)

    def notificar_turno(role, texto):
        if ao_turno_concluido:
            ao_turno_concluido(role, texto)

    if not esta_disponivel():
        print(f"[RESERVA] {motivo_indisponivel()}")
        return False

    try:
        ferramentas = cerebro.montar_ferramentas(pacotes_registrados)

    except Exception as erro:
        print(f"[RESERVA] Não foi possível montar as ferramentas: {erro}")
        ferramentas = []

    print(
        "[RESERVA] Assumindo a conversa com "
        f"{len(ferramentas)} ferramentas disponíveis."
    )

    historico = list(historico_inicial or [])
    assumiu_algum_turno = False

    while deve_continuar():
        try:
            ouvido = escuta.ouvir(
                deve_continuar,
                fila_bloco_externa=fila_bloco_externa,
                audio_wav_pronto=audio_primeiro_turno,
            )

            # Só a primeira escuta usa o áudio pronto — a partir daqui
            # volta a ouvir ao vivo, mesmo que o Gemini continue mudo.
            audio_primeiro_turno = None

        except Exception as erro:
            print(f"[RESERVA] Falha ao ouvir: {erro}")
            return assumiu_algum_turno

        # None = ninguém falou dentro do tempo de espera, ou a
        # chamada foi encerrada. Volta ao laço, que reavalia
        # deve_continuar().
        if ouvido is None:
            continue

        sucesso_texto, texto_usuario = ouvido

        if not sucesso_texto:
            print(f"[RESERVA] {texto_usuario}")
            continue

        status("Pensando...")
        notificar_turno("user", texto_usuario)

        historico = cerebro.podar_historico(
            historico + [{"role": "user", "content": texto_usuario}]
        )

        try:
            sucesso, resposta, historico, encerrar = cerebro.responder(
                historico,
                pacotes_registrados,
                ferramentas,
                ao_executar_ferramenta=lambda nome: status(
                    f"Executando {nome}..."
                ),
            )

        except Exception as erro:
            print(f"[RESERVA] Falha ao pensar: {erro}")
            continue

        if not deve_continuar():
            break

        status("Respondendo...")

        sucesso_fala, erro_fala = fala.falar(resposta)

        if not sucesso_fala:
            print(f"[RESERVA] Falha ao falar: {erro_fala}")

        # Notifica o que foi REALMENTE falado, sucesso ou não — mesmo
        # uma mensagem de erro faz parte da conversa que o usuário
        # ouviu de verdade.
        notificar_turno("assistant", resposta)

        assumiu_algum_turno = True

        # O usuário pediu para encerrar: a despedida já foi falada
        # acima, então agora o modo reserva termina de verdade.
        if encerrar:
            break

        status("Ouvindo...")

    print("[RESERVA] Encerrando o modo reserva.")

    return assumiu_algum_turno
