# Detector de ativação por voz — escuta o microfone continuamente,
# 100% local (nada é enviado pra nuvem, nenhuma conta ou chave de API
# é necessária), enquanto NENHUMA chamada com o Gemini está ativa, e
# dispara um callback assim que reconhece a palavra-chave configurada
# (ver ativacao_voz.config.NOME_ATIVACAO).
#
# Usa Vosk (pacote vosk) — reconhecimento de voz genérico e offline,
# não um motor de wake-word dedicado. Escolhido especificamente por
# não exigir nenhuma conta/chave de API (ao contrário do Porcupine da
# Picovoice, a alternativa considerada antes desta), a pedido
# explícito do usuário: reconhece o que foi dito e compara com o
# nome, sem depender de nenhum serviço externo além do download único
# do modelo (feito automaticamente pelo próprio pacote vosk, na
# primeira vez, de alphacephei.com — sem cadastro nenhum). Modelo
# "small" em português (~31MB) confirmado ao vivo antes de escrever
# este arquivo: baixa e carrega sozinho na primeira chamada a
# Model(lang="pt"), fica em cache local depois disso.
#
# Reaproveita sounddevice pra ler o microfone (mesma biblioteca já
# usada pelo resto do projeto), em modo de leitura bloqueante — mesma
# escolha e mesmo motivo já documentados quando isso foi feito pra
# webcam compartilhada (jarvis/servicos/visao/captura_camera.py).
import difflib
import json
import re
import threading
import unicodedata

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from . import config


# Taxa de amostragem e tamanho de bloco esperados pelo modelo Vosk —
# 16kHz é o padrão dos modelos "small" do Vosk (confirmado ao vivo:
# funcionou sem erro no teste real feito antes de implementar este
# arquivo). Bloco de 4000 amostras (~0,25s) dá uma granularidade
# razoável entre latência de detecção e overhead de processamento.
TAXA_AMOSTRAGEM_VOSK = 16000
TAMANHO_BLOCO_VOSK = 4000

# Corte de similaridade pro fallback difflib — mesmo valor já usado
# em jarvis/pacotes/fechar_app/processos.py e jarvis/pacotes/discord_jarvis/contatos.py pra
# tolerar imprecisões do reconhecimento de voz.
CORTE_SIMILARIDADE = 0.72

# Modelo Vosk — pesado (carrega um modelo de reconhecimento de voz
# inteiro na memória, e pode precisar baixar ~31MB na primeira vez).
# Carregado uma única vez por processo e reaproveitado em todo
# pausar()/retomar() — só o KaldiRecognizer (leve) é recriado a cada
# ciclo, dentro de _loop_deteccao.
_modelo = None

_stream = None  # sounddevice.RawInputStream ativo, ou None
_thread = None  # thread de fundo rodando o loop de detecção, ou None
_parar_evento = threading.Event()

# Callback registrado por iniciar() (chamado uma única vez, em
# main.py) — guardado à parte do ciclo de vida do stream, pra
# que pausar()/retomar() (chamados por GeminiLiveWorker a cada
# chamada, ver jarvis/gemini/cliente_live.py) não precisem recebê-lo de
# novo a cada vez. Chamado numa thread de fundo (nunca a thread da
# GUI) — quem registra o callback é responsável por só fazer coisas
# thread-safe dentro dele (ex: emitir um Signal do sinalizador).
_callback_ativacao = None


# Mesma técnica de normalização já usada em vários outros pacotes
# deste projeto (jarvis/pacotes/fechar_app/processos.py,
# jarvis/pacotes/discord_jarvis/contatos.py, etc.) — copiada aqui de forma
# independente, não importada, seguindo a convenção do projeto.
def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


# Confere se uma palavra-alvo (já normalizada) aparece entre as
# palavras reconhecidas — exata ou, se não bater exato, com uma
# tolerância via difflib (mesmo corte já usado em outros pacotes) pra
# absorver pequenas imprecisões do reconhecimento de voz genérico
# (que não é um motor de wake-word dedicado, então erra mais que um
# Porcupine erraria).
def _palavra_esta_presente(palavra_alvo, palavras_texto):
    if palavra_alvo in palavras_texto:
        return True

    return bool(
        difflib.get_close_matches(
            palavra_alvo,
            palavras_texto,
            n=1,
            cutoff=CORTE_SIMILARIDADE,
        )
    )


# Confere se o texto reconhecido pelo Vosk corresponde à frase de
# ativação configurada (normalizado — acento/caixa-insensível).
# Tenta primeiro a frase inteira como substring contígua (cobre o
# caso comum de uma frase dita exatamente igual, ou uma única
# palavra de ativação). Se a ativação tiver mais de uma palavra e
# isso não bater, cai pra exigir que TODAS as palavras-alvo apareçam
# em algum lugar do texto reconhecido, não necessariamente
# adjacentes — cobre frases naturais como "iniciar A chamada" (com
# um artigo no meio), que não bateriam como substring exato de
# "iniciar chamada".
def _contem_palavra_ativacao(texto_reconhecido):
    alvo = _normalizar(config.NOME_ATIVACAO)

    if not alvo:
        return False

    texto_normalizado = _normalizar(texto_reconhecido)

    if not texto_normalizado:
        return False

    if alvo in texto_normalizado:
        return True

    palavras_alvo = alvo.split(" ")
    palavras_texto = texto_normalizado.split(" ")

    if len(palavras_alvo) > 1:
        return all(
            _palavra_esta_presente(
                palavra_alvo,
                palavras_texto,
            )
            for palavra_alvo in palavras_alvo
        )

    return _palavra_esta_presente(
        alvo,
        palavras_texto,
    )


def _obter_modelo():
    global _modelo

    if _modelo is None:
        # Baixa (só na primeira vez, ~31MB) e carrega o modelo
        # "small" em português — confirmado ao vivo antes de usar.
        _modelo = Model(lang="pt")

    return _modelo


# Loop principal, rodando na thread de fundo criada por _abrir(). O
# carregamento do modelo (potencialmente lento — download na primeira
# vez) acontece AQUI DENTRO, não em _abrir()/iniciar(), de propósito:
# assim main.py nunca trava esperando isso na inicialização do
# app. Termina de três jeitos: (1) a palavra de ativação é
# reconhecida — chama o callback e para sozinho; (2) pausar() pede
# pra parar (_parar_evento.set()) antes ou depois do modelo carregar;
# (3) falha ao carregar o modelo ou abrir o microfone. Em todos os
# casos, o bloco finally libera o microfone (se chegou a abrir) e
# zera as referências globais — assim iniciar()/retomar() sempre
# encontram um estado limpo.
def _loop_deteccao():
    global _stream, _thread

    try:
        try:
            modelo = _obter_modelo()

        except Exception as erro:
            print(
                f"[ativacao_voz] Não foi possível carregar o modelo "
                f"de reconhecimento de voz: {erro}"
            )
            return

        # pausar() pode ter sido chamado enquanto o modelo carregava
        # (só relevante na primeiríssima vez, durante o download) —
        # nesse caso nem chega a abrir o microfone.
        if _parar_evento.is_set():
            return

        reconhecedor = KaldiRecognizer(
            modelo,
            TAXA_AMOSTRAGEM_VOSK,
        )

        try:
            _stream = sd.RawInputStream(
                samplerate=TAXA_AMOSTRAGEM_VOSK,
                blocksize=TAMANHO_BLOCO_VOSK,
                dtype="int16",
                channels=1,
            )

        except Exception as erro:
            print(
                f"[ativacao_voz] Não foi possível abrir o "
                f"microfone: {erro}"
            )
            return

        with _stream:
            while not _parar_evento.is_set():
                dados, _overflowed = _stream.read(
                    TAMANHO_BLOCO_VOSK
                )

                dados_bytes = bytes(dados)

                if reconhecedor.AcceptWaveform(dados_bytes):
                    texto = json.loads(
                        reconhecedor.Result()
                    ).get("text", "")
                else:
                    texto = json.loads(
                        reconhecedor.PartialResult()
                    ).get("partial", "")

                if texto and _contem_palavra_ativacao(texto):
                    if _callback_ativacao:
                        _callback_ativacao()

                    break

    finally:
        _stream = None
        _thread = None


def _abrir():
    global _thread

    if _thread is not None:
        return True  # já escutando (ou carregando o modelo) — idempotente

    _parar_evento.clear()

    _thread = threading.Thread(
        target=_loop_deteccao,
        daemon=True,
    )

    _thread.start()

    return True


# Chamado uma única vez, em main.py, logo depois que a janela
# principal existe. Registra o callback (chamado numa thread de
# fundo assim que a palavra de ativação é reconhecida) e começa a
# escutar. Retorna imediatamente (não espera o modelo carregar) —
# ver _loop_deteccao.
def iniciar(callback_ativacao):
    global _callback_ativacao

    _callback_ativacao = callback_ativacao

    return _abrir()


# Para de escutar e libera o microfone — chamado por GeminiLiveWorker
# IMEDIATAMENTE antes de abrir seu próprio stream de microfone, pra
# nunca haver dois handles de áudio concorrentes (mesmo cuidado já
# tomado com a câmera em jarvis/servicos/visao/captura_camera.py). Idempotente: não
# faz nada se já estiver parado. Bloqueia até a thread de fato
# terminar — o timeout é generoso (30s) porque, na primeiríssima
# ativação do app, a thread pode estar no meio do download do
# modelo (~31MB); em qualquer execução seguinte (modelo já em cache
# local), a thread termina quase instantaneamente.
def pausar():
    _parar_evento.set()

    thread_atual = _thread

    if thread_atual is not None:
        thread_atual.join(timeout=30)


# Volta a escutar — chamado por GeminiLiveWorker quando uma chamada
# termina (ver o cleanup em executar(), jarvis/gemini/cliente_live.py).
# Reaproveita o callback já registrado por iniciar() e o modelo já
# carregado em memória (_obter_modelo() só recarrega se necessário).
# Idempotente.
def retomar():
    _abrir()


def esta_ativo():
    return _thread is not None
