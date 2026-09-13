import asyncio
import io
import json
import os
import sys
import tempfile
import time
import wave

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import concurrent.futures

import numpy as np

from jarvis.cerebro.voz_local import audio_wav
from jarvis.cerebro.voz_local import config as config_local
from jarvis.cerebro.voz_local.cliente_local import VozLocalWorker, TAXA_ENTRADA, BLOCO
from jarvis.cerebro.voz_local.mqtt_voz import ClienteVozLocal

TEXTO_DA_RESPOSTA = "Seu nome é Massaki, e hoje está fazendo sol."

import jarvis.nucleo.config as nucleo_config


aprovados = 0
reprovados = 0


def checar(condicao, descricao):
    global aprovados, reprovados

    if condicao:
        aprovados += 1
        print(f"  OK   {descricao}")

    else:
        reprovados += 1
        print(f"  FALHA {descricao}")


def titulo(texto):
    print(f"\n=== {texto} ===")


def testar_paridade():
    titulo("1. Paridade de API entre os três cérebros de voz")

    from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker
    from jarvis.cerebro.openai_realtime import OpenAIRealtimeWorker

    sinais = [
        "status_recebido",
        "erro_recebido",
        "chamada_encerrada",
        "nivel_audio",
        "solicitou_encerramento",
        "solicitou_reconexao",
        "session_handle_atualizado",
        "solicitou_hibernacao",
    ]

    metodos = [
        "parar",
        "solicitar_analise_tela",
        "solicitar_analise_camera",
        "enviar_texto_da_ui",
        "enviar_imagem_da_ui",
        "run",
    ]

    for nome in sinais + metodos:
        checar(
            hasattr(VozLocalWorker, nome),
            f"VozLocalWorker tem {nome}",
        )

    import inspect

    assinaturas = {
        classe.__name__: list(
            inspect.signature(classe.__init__).parameters
        )
        for classe in (
            GeminiLiveWorker,
            OpenAIRealtimeWorker,
            VozLocalWorker,
        )
    }

    checar(
        assinaturas["VozLocalWorker"] == assinaturas["GeminiLiveWorker"],
        f"construtor idêntico ao do Gemini {assinaturas['VozLocalWorker']}",
    )

    checar(
        assinaturas["VozLocalWorker"] == assinaturas["OpenAIRealtimeWorker"],
        "construtor idêntico ao da OpenAI",
    )


def testar_provedor():
    titulo("2. Seleção do cérebro por PROVEDOR_IA")

    import jarvis.ui.janela_principal as janela

    from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker
    from jarvis.cerebro.openai_realtime import OpenAIRealtimeWorker

    original = nucleo_config.CAMINHO_ENV

    pasta = Path(tempfile.mkdtemp(prefix="jarvis-teste-env-"))
    falso_env = pasta / ".env"

    casos = [
        ("gemini", "gemini", GeminiLiveWorker),
        ("openai", "openai", OpenAIRealtimeWorker),
        ("local", "local", VozLocalWorker),
        ("LOCAL", "local", VozLocalWorker),
        ("  local  ", "local", VozLocalWorker),
        ("locall", "gemini", GeminiLiveWorker),
        ("", "gemini", GeminiLiveWorker),
    ]

    try:
        nucleo_config.CAMINHO_ENV = falso_env

        for valor, esperado, classe in casos:
            falso_env.write_text(
                f"PROVEDOR_IA={valor}\n",
                encoding="utf-8",
            )

            checar(
                nucleo_config.provedor_ativo() == esperado,
                f'PROVEDOR_IA="{valor}" resolve para "{esperado}"',
            )

            checar(
                janela._classe_do_worker() is classe,
                f'PROVEDOR_IA="{valor}" escolhe {classe.__name__}',
            )

        falso_env.write_text("OUTRA=1\n", encoding="utf-8")

        checar(
            nucleo_config.provedor_ativo() == "gemini",
            "sem PROVEDOR_IA no .env, cai no Gemini",
        )

        checar(
            nucleo_config.usar_provedor_openai() is False
            and nucleo_config.usar_provedor_local() is False,
            "usar_provedor_openai/local seguem coerentes",
        )

    finally:
        nucleo_config.CAMINHO_ENV = original

        falso_env.unlink(missing_ok=True)
        pasta.rmdir()


def testar_selects_de_cerebro():
    titulo("2b. Os dois selects de cérebro oferecem as mesmas opções")

    from jarvis.ui import painel_provedor

    opcoes_config = [
        campo["opcoes"]
        for campo in nucleo_config.config_schema()
        if campo["nome"] == "PROVEDOR_IA"
    ][0]

    checar(
        list(painel_provedor.OPCOES) == list(opcoes_config),
        "tela principal e tela de configurações oferecem a MESMA lista",
    )

    print(
        f"       (opções: {[valor for valor, _ in painel_provedor.OPCOES]})"
    )

    for valor, rotulo in painel_provedor.OPCOES:
        checar(
            valor in nucleo_config.PROVEDORES_VALIDOS,
            f'a opção "{rotulo}" ({valor}) é um provedor reconhecido',
        )

    checar(
        len(painel_provedor.OPCOES) == len(nucleo_config.PROVEDORES_VALIDOS),
        "e todo provedor reconhecido aparece como opção "
        f"({len(nucleo_config.PROVEDORES_VALIDOS)})",
    )

    original = nucleo_config.CAMINHO_ENV

    pasta = Path(tempfile.mkdtemp(prefix="jarvis-teste-painel-"))
    falso_env = pasta / ".env"

    try:
        nucleo_config.CAMINHO_ENV = falso_env
        painel_provedor.CAMINHO_ENV = falso_env

        falso_env.write_text("PROVEDOR_IA=local\n", encoding="utf-8")

        painel = painel_provedor.PainelProvedor()

        itens = [
            painel.combo.itemData(i) for i in range(painel.combo.count())
        ]

        checar(
            itens == [valor for valor, _ in painel_provedor.OPCOES],
            f"o QComboBox real é montado com todas as opções ({itens})",
        )

        checar(
            painel.combo.currentData() == "local",
            "e já vem selecionado no cérebro que está no .env",
        )

        checar(
            painel_provedor._ler_provedor_atual() == "local",
            "a leitura reconhece o servidor local em vez de cair no Gemini",
        )

        painel.deleteLater()

    finally:
        nucleo_config.CAMINHO_ENV = original
        painel_provedor.CAMINHO_ENV = original

        falso_env.unlink(missing_ok=True)
        pasta.rmdir()


def testar_wav():
    titulo("3. Conversão PCM <-> WAV")

    pcm = b"\x01\x02" * 16000

    wav = audio_wav.pcm_para_wav(pcm, 16000, 1)

    checar(
        wav[:4] == b"RIFF" and wav[8:12] == b"WAVE",
        "pcm_para_wav gera um RIFF/WAVE válido",
    )

    volta, taxa, canais = audio_wav.wav_para_pcm(wav)

    checar(volta == pcm, "ida e volta preserva as amostras byte a byte")
    checar(taxa == 16000 and canais == 1, "taxa e canais preservados")

    checar(
        abs(audio_wav.duracao_segundos(pcm, 16000, 1) - 1.0) < 0.001,
        "duracao_segundos calcula 1,0s corretamente",
    )

    _, taxa24, _ = audio_wav.wav_para_pcm(
        audio_wav.pcm_para_wav(pcm, 24000, 1)
    )

    checar(taxa24 == 24000, "taxa de 24 kHz lida do cabeçalho, não presumida")

    _, _, canais2 = audio_wav.wav_para_pcm(
        audio_wav.pcm_para_wav(pcm, 16000, 2)
    )

    checar(canais2 == 2, "WAV estéreo reportado com 2 canais")

    def erro_de(dados):
        try:
            audio_wav.wav_para_pcm(dados)

        except ValueError as erro:
            return str(erro)

        return None

    checar(erro_de(b"") is not None, "WAV vazio vira ValueError legível")

    checar(
        erro_de(b"nao sou um wav") is not None,
        "lixo binário vira ValueError legível",
    )

    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(1)
        arquivo.setframerate(16000)
        arquivo.writeframes(b"\x01" * 1000)

    mensagem = erro_de(buffer.getvalue())

    checar(
        mensagem is not None and "8 bits" in mensagem,
        f"WAV de 8 bits recusado com mensagem clara ({mensagem})",
    )

    checar(
        erro_de(audio_wav.pcm_para_wav(b"", 16000, 1)) is not None,
        "WAV sem amostras recusado",
    )


def _bloco(nivel_bruto):
    amostra = int(nivel_bruto * 32767)

    return amostra.to_bytes(2, "little", signed=True) * BLOCO


def _niveis():
    alto = _bloco(0.5)
    baixo = _bloco(0.0005)

    return (
        VozLocalWorker.calcular_nivel_audio(alto),
        VozLocalWorker.calcular_nivel_audio(baixo),
    )


def testar_vad(worker):
    titulo("4. Detecção de fim de fala (VAD por silêncio)")

    nivel_alto, nivel_baixo = _niveis()

    checar(
        nivel_alto >= config_local.LIMIAR_VOZ,
        f"bloco de fala fica acima do limiar ({nivel_alto:.3f} >= "
        f"{config_local.LIMIAR_VOZ})",
    )

    checar(
        nivel_baixo < config_local.LIMIAR_VOZ,
        f"bloco de silêncio fica abaixo do limiar ({nivel_baixo:.3f} < "
        f"{config_local.LIMIAR_VOZ})",
    )

    fala = _bloco(0.5)
    silencio = _bloco(0.0005)

    duracao_bloco = audio_wav.duracao_segundos(fala, TAXA_ENTRADA, 1)

    blocos_silencio = int(config_local.SILENCIO_SEGUNDOS / duracao_bloco) + 2
    blocos_fala = int(1.5 / duracao_bloco)

    async def rodar(sequencia):
        fila = asyncio.Queue()

        for bloco in sequencia:
            fila.put_nowait(bloco)

        worker.ativo = True

        return await asyncio.wait_for(
            worker._capturar_frase(fila),
            timeout=10,
        )

    sequencia = (
        [silencio] * 5
        + [fala] * blocos_fala
        + [silencio] * blocos_silencio
    )

    pcm = asyncio.run(rodar(sequencia))

    checar(pcm is not None, "fala cercada de silêncio é capturada")

    if pcm:
        duracao = audio_wav.duracao_segundos(pcm, TAXA_ENTRADA, 1)

        checar(
            duracao >= 1.5,
            f"a frase capturada tem a duração da fala ({duracao:.2f}s >= 1.5s)",
        )

        checar(
            duracao > 1.5 + (config_local.BLOCOS_PRE_FALA - 1) * duracao_bloco,
            "os blocos de pré-fala entraram na frase (não corta a 1ª sílaba)",
        )

        checar(
            duracao < 1.5 + config_local.SILENCIO_SEGUNDOS,
            f"o silêncio final foi aparado ({duracao:.2f}s < "
            f"{1.5 + config_local.SILENCIO_SEGUNDOS:.2f}s)",
        )

    async def so_silencio():
        fila = asyncio.Queue()

        for bloco in [silencio] * 30:
            fila.put_nowait(bloco)

        worker.ativo = True

        tarefa = asyncio.create_task(worker._capturar_frase(fila))

        await asyncio.sleep(0.6)
        worker.ativo = False

        return await asyncio.wait_for(tarefa, timeout=5)

    checar(
        asyncio.run(so_silencio()) is None,
        "silêncio puro não gera nenhum envio",
    )

    curta = (
        [silencio] * 3
        + [fala] * 2
        + [silencio] * blocos_silencio
    )

    checar(
        asyncio.run(rodar(curta)) is None,
        "ruído mais curto que DURACAO_MINIMA_SEGUNDOS é descartado",
    )

    limite_original = config_local.DURACAO_MAXIMA_SEGUNDOS
    config_local.DURACAO_MAXIMA_SEGUNDOS = 1.0

    try:
        pcm_teto = asyncio.run(rodar([fala] * 200))

        duracao_teto = audio_wav.duracao_segundos(pcm_teto or b"", TAXA_ENTRADA, 1)

        checar(
            pcm_teto is not None and duracao_teto < 1.5,
            f"ruído contínuo é cortado pelo teto ({duracao_teto:.2f}s), "
            "não grava sem parar",
        )

    finally:
        config_local.DURACAO_MAXIMA_SEGUNDOS = limite_original


def _fala_sapi_16k():
    import tempfile
    import wave

    try:
        import win32com.client

        destino = Path(tempfile.gettempdir()) / "jarvis_teste_vad.wav"

        voz = win32com.client.Dispatch("SAPI.SpVoice")
        fluxo = win32com.client.Dispatch("SAPI.SpFileStream")
        fluxo.Open(str(destino), 3)
        voz.AudioOutputStream = fluxo
        voz.Speak(
            "Bom dia. Este é um teste do detector de voz do assistente."
        )
        fluxo.Close()

        with wave.open(str(destino), "rb") as w:
            pcm = w.readframes(w.getnframes())
            taxa = w.getframerate()
            canais = w.getnchannels()

    except Exception as erro:
        print(f"  (SAPI indisponível: {erro})")

        return None

    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    if canais > 1:
        x = x.reshape(-1, canais).mean(axis=1)

    if taxa != TAXA_ENTRADA:
        n = int(len(x) * TAXA_ENTRADA / taxa)
        x = np.interp(
            np.linspace(0, len(x) - 1, n), np.arange(len(x)), x
        )

    return x.astype(np.float32)


def _ruido_motor(segundos, hz=90, amplitude=0.6):
    t = np.arange(int(TAXA_ENTRADA * segundos)) / TAXA_ENTRADA
    onda = sum(
        pow(0.6, k) * np.sin(2 * np.pi * hz * (k + 1) * t) for k in range(4)
    )

    return (onda / max(abs(onda).max(), 1e-9) * amplitude).astype(np.float32)


def _ruido_musica(segundos, amplitude=0.6):
    t = np.arange(int(TAXA_ENTRADA * segundos)) / TAXA_ENTRADA
    onda = sum(
        np.sin(2 * np.pi * f * t + 3 * np.sin(2 * np.pi * 5 * t))
        for f in (220, 277, 330, 440)
    )

    return (onda / max(abs(onda).max(), 1e-9) * amplitude).astype(np.float32)


def _ruido_branco(segundos, amplitude=0.35):
    n = int(TAXA_ENTRADA * segundos)

    return (np.random.randn(n) * amplitude).clip(-1, 1).astype(np.float32)


def _para_pcm(x):
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


def _blocos_de(x):
    pcm = _para_pcm(x)
    tamanho = BLOCO * 2

    return [
        pcm[i:i + tamanho]
        for i in range(0, len(pcm) - tamanho + 1, tamanho)
    ]


def _proporcao_com_fala(detector, sinal):
    detector.zerar()
    blocos = _blocos_de(sinal)

    if not blocos:
        return 0.0

    return sum(detector.tem_fala(b) for b in blocos) / len(blocos)


def testar_vad_silero(worker):
    titulo("4b. Detecção de fala por conteúdo (Silero VAD)")

    from jarvis.cerebro.voz_local import vad_silero

    try:
        detector = vad_silero.DetectorDeFala()

    except vad_silero.VadIndisponivel as erro:
        checar(False, f"o detector de fala carrega ({erro})")

        return

    checar(True, f"modelo carregado ({Path(detector.caminho_modelo).name})")

    for nome, sinal in [
        ("motor/moto 90 Hz", _ruido_motor(3, 90, 0.6)),
        ("ventilador 200 Hz", _ruido_motor(3, 200, 0.6)),
        ("música", _ruido_musica(3, 0.6)),
        ("ruído branco forte", _ruido_branco(3, 0.35)),
        ("silêncio digital", np.zeros(TAXA_ENTRADA * 3, dtype=np.float32)),
    ]:
        proporcao = _proporcao_com_fala(detector, sinal)
        pico = float(max(abs(sinal))) if len(sinal) else 0.0

        checar(
            proporcao <= 0.25,
            f"{nome} (pico {pico:.2f}) NÃO é fala "
            f"({proporcao * 100:.1f}% dos blocos)",
        )

        if pico > 0.2:
            amplitude = sum(
                VozLocalWorker.calcular_nivel_audio(b)
                >= config_local.LIMIAR_VOZ
                for b in _blocos_de(sinal)
            ) / max(len(_blocos_de(sinal)), 1)

            checar(
                amplitude > proporcao,
                f"  (o critério antigo, por volume, chamaria "
                f"{amplitude * 100:.0f}% disso de fala)",
            )

    fala = _fala_sapi_16k()

    if fala is None:
        checar(False, "SAPI gerou a fala de teste")

        return

    proporcao_fala = _proporcao_com_fala(detector, fala)

    checar(
        proporcao_fala >= 0.4,
        f"voz normal É reconhecida como fala "
        f"({proporcao_fala * 100:.1f}% dos blocos)",
    )

    n = min(len(fala), TAXA_ENTRADA * 5)
    segundos = n / TAXA_ENTRADA

    for nome, ruido in [
        ("motor 90 Hz", _ruido_motor(segundos, 90, 0.35)),
        ("ventilador 200 Hz", _ruido_motor(segundos, 200, 0.3)),
        ("música", _ruido_musica(segundos, 0.3)),
    ]:
        mistura = (fala[:n] * 0.8 + ruido[:n]).astype(np.float32)
        proporcao = _proporcao_com_fala(detector, mistura)

        checar(
            proporcao >= 0.4,
            f"voz + {nome} continua sendo fala "
            f"({proporcao * 100:.1f}% dos blocos)",
        )

    detector.zerar()
    blocos = _blocos_de(fala)
    inicio = time.perf_counter()

    for bloco in blocos:
        detector.tem_fala(bloco)

    total = time.perf_counter() - inicio
    por_bloco_ms = total / len(blocos) * 1000
    duracao_bloco_ms = BLOCO / TAXA_ENTRADA * 1000

    checar(
        por_bloco_ms < duracao_bloco_ms / 10,
        f"inferência cabe no tempo real: {por_bloco_ms:.3f} ms por bloco "
        f"de {duracao_bloco_ms:.0f} ms ({duracao_bloco_ms / por_bloco_ms:.0f}x)",
    )

    detector.zerar()
    pcm_fala = _para_pcm(fala)
    pedaco = 700 * 2

    algum = any(
        detector.tem_fala(pcm_fala[i:i + pedaco])
        for i in range(0, len(pcm_fala) - pedaco + 1, pedaco)
    )

    checar(algum, "blocos de tamanho arbitrário (700 amostras) funcionam")

    checar(
        detector.probabilidade(b"") == 0.0
        and detector.probabilidade(_para_pcm(fala[:100])) == 0.0,
        "bloco vazio ou menor que uma janela devolve 0.0 sem estourar",
    )

    duracao_bloco = BLOCO / TAXA_ENTRADA
    blocos_para_fechar = int(config_local.SILENCIO_SEGUNDOS / duracao_bloco) + 4

    ruido_fundo = _ruido_motor(20, 90, 0.4)
    n_fala = min(len(fala), TAXA_ENTRADA * 3)
    fala_com_ruido = (
        fala[:n_fala] * 0.8 + ruido_fundo[:n_fala]
    ).astype(np.float32)

    sequencia = (
        _blocos_de(ruido_fundo[:TAXA_ENTRADA // 2])
        + _blocos_de(fala_com_ruido)
        + _blocos_de(
            ruido_fundo[: int(TAXA_ENTRADA * duracao_bloco * blocos_para_fechar)]
        )
    )

    async def capturar(com_detector):
        fila = asyncio.Queue()

        for bloco in sequencia:
            fila.put_nowait(bloco)

        worker.detector_fala = detector if com_detector else None
        worker.ativo = True

        tarefa = asyncio.create_task(worker._capturar_frase(fila))

        try:
            limite = time.perf_counter() + 2.5

            while time.perf_counter() < limite:
                if tarefa.done():
                    return tarefa.result()

                await asyncio.sleep(0.05)

            return "NAO_FECHOU"

        finally:
            worker.ativo = False
            worker.detector_fala = None

            if not tarefa.done():
                try:
                    await asyncio.wait_for(tarefa, timeout=3)

                except (asyncio.TimeoutError, asyncio.CancelledError):
                    tarefa.cancel()

    pcm = asyncio.run(capturar(True))

    checar(
        pcm not in (None, "NAO_FECHOU"),
        "com o Silero, a frase FECHA mesmo com o ruído continuando",
    )

    if isinstance(pcm, bytes):
        duracao = audio_wav.duracao_segundos(pcm, TAXA_ENTRADA, 1)

        checar(
            duracao < (n_fala / TAXA_ENTRADA)
            + config_local.SILENCIO_SEGUNDOS
            + 1.0,
            f"e não arrastou o ruído junto ({duracao:.2f}s de áudio)",
        )

    antigo = asyncio.run(capturar(False))

    checar(
        antigo == "NAO_FECHOU",
        "e o critério antigo (volume) NÃO fechava — é o bug relatado "
        f"(resultado: {'não fechou' if antigo == 'NAO_FECHOU' else antigo!r})",
    )

    worker.detector_fala = None
    bloco_alto = _bloco(0.5)
    bloco_baixo = _bloco(0.0005)

    checar(
        worker._bloco_tem_fala(
            bloco_alto, VozLocalWorker.calcular_nivel_audio(bloco_alto)
        )
        and not worker._bloco_tem_fala(
            bloco_baixo, VozLocalWorker.calcular_nivel_audio(bloco_baixo)
        ),
        "sem detector, cai para o critério de volume (modo de emergência)",
    )

    class DetectorQuebrado:
        def zerar(self):
            pass

        def tem_fala(self, bloco):
            raise RuntimeError("onnxruntime explodiu")

    worker.detector_fala = DetectorQuebrado()
    resultado = worker._bloco_tem_fala(
        bloco_alto, VozLocalWorker.calcular_nivel_audio(bloco_alto)
    )

    checar(
        resultado is True and worker.detector_fala is None,
        "erro na inferência não estoura: desliga o detector e segue por volume",
    )

    worker.detector_fala = None


def _saida_falsa(escritos, atraso=0.004):
    class SaidaFalsa:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, pedaco):
            escritos.append(len(pedaco))
            time.sleep(atraso)

    return SaidaFalsa


def _tocar(worker, pcm_resposta, blocos_microfone, atraso=0.004):
    import jarvis.cerebro.voz_local.cliente_local as modulo

    escritos = []
    wav = audio_wav.pcm_para_wav(pcm_resposta, TAXA_ENTRADA, 1)
    sobraram = []

    async def principal():
        fila = asyncio.Queue()

        async def alimentar():
            for bloco in blocos_microfone:
                fila.put_nowait(bloco)

                await asyncio.sleep(atraso)

        alimentador = asyncio.create_task(alimentar())
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        try:
            await worker._reproduzir_resposta(wav, fila, executor)

            sobraram.append(fila.qsize())

        finally:
            alimentador.cancel()
            executor.shutdown(wait=False)

    sd_original = modulo.sd.RawOutputStream
    modulo.sd.RawOutputStream = _saida_falsa(escritos, atraso)
    worker.ativo = True

    try:
        asyncio.run(principal())

    finally:
        modulo.sd.RawOutputStream = sd_original

    return sum(escritos), (sobraram[0] if sobraram else -1)


def testar_barge_in(worker):
    titulo("4c. Interrupção da fala (barge-in) no modo local")

    import jarvis.cerebro.voz_local.cliente_local as modulo
    from jarvis.cerebro.voz_local import vad_silero

    try:
        worker.detector_fala = vad_silero.DetectorDeFala()

    except vad_silero.VadIndisponivel as erro:
        checar(False, f"detector disponível para o barge-in ({erro})")

        return

    fala = _fala_sapi_16k()

    if fala is None:
        checar(False, "SAPI gerou a fala de teste")

        return

    resposta_pcm = _para_pcm(_ruido_musica(6, 0.3))
    blocos_fala = _blocos_de(fala)
    blocos_ruido = _blocos_de(_ruido_motor(6, 90, 0.6))

    carencia_original = modulo.CARENCIA_INTERRUPCAO_SEGUNDOS
    atraso_original = modulo.ATRASO_REABRIR_MICROFONE

    modulo.CARENCIA_INTERRUPCAO_SEGUNDOS = 0.02
    modulo.ATRASO_REABRIR_MICROFONE = 0.05

    try:
        worker.interrupcao_habilitada = True
        worker.interrupcoes_na_chamada = 0
        worker._blocos_apos_interrupcao = []

        escritos, _sobra = _tocar(worker, resposta_pcm, blocos_fala)

        checar(
            escritos < len(resposta_pcm),
            f"voz do usuário corta a reprodução ({escritos} de "
            f"{len(resposta_pcm)} bytes tocados)",
        )
        checar(
            worker.interrupcoes_na_chamada == 1,
            f"e o contador de diagnóstico sobe "
            f"({worker.interrupcoes_na_chamada})",
        )
        checar(
            not worker.alfred_falando,
            "o microfone é liberado na hora (alfred_falando volta a False)",
        )

        checar(
            len(worker._blocos_apos_interrupcao) > 0,
            f"os blocos que o vigia consumiu viram pré-fala "
            f"({len(worker._blocos_apos_interrupcao)} blocos)",
        )

        guardados = list(worker._blocos_apos_interrupcao)

        async def so_consumir_pre_fala():
            fila = asyncio.Queue()
            worker.ativo = True
            tarefa = asyncio.create_task(worker._capturar_frase(fila))
            await asyncio.sleep(0.3)
            worker.ativo = False

            try:
                await asyncio.wait_for(tarefa, timeout=3)

            except Exception:
                pass

        asyncio.run(so_consumir_pre_fala())

        checar(
            worker._blocos_apos_interrupcao == [],
            "e a captura seguinte consome essa pré-fala (não fica presa)",
        )
        checar(
            guardados,
            "os blocos guardados eram os do microfone, não uma lista vazia",
        )

        worker.interrupcao_habilitada = True
        worker.interrupcoes_na_chamada = 0
        worker._blocos_apos_interrupcao = []

        escritos, _sobra = _tocar(worker, resposta_pcm, blocos_ruido)

        checar(
            escritos == len(resposta_pcm),
            f"ruído de motor NÃO corta a fala ({escritos} de "
            f"{len(resposta_pcm)} bytes tocados)",
        )
        checar(
            worker.interrupcoes_na_chamada == 0,
            "e nenhuma interrupção é contabilizada",
        )

        silencio = _blocos_de(np.zeros(TAXA_ENTRADA, dtype=np.float32))
        estalo = (
            silencio[:5]
            + blocos_fala[:modulo.BLOCOS_FALA_PARA_INTERROMPER - 2]
            + silencio[:20]
        )

        worker.interrupcoes_na_chamada = 0
        escritos, _sobra = _tocar(worker, resposta_pcm, estalo)

        checar(
            worker.interrupcoes_na_chamada == 0
            and escritos == len(resposta_pcm),
            f"fala curta demais não interrompe — exige "
            f"{modulo.BLOCOS_FALA_PARA_INTERROMPER} blocos consecutivos",
        )

        worker.interrupcao_habilitada = False
        worker.interrupcoes_na_chamada = 0

        escritos, na_fila = _tocar(worker, resposta_pcm, blocos_fala)

        checar(
            escritos == len(resposta_pcm),
            f"com a interrupção desligada, a fala vai até o fim "
            f"({escritos} de {len(resposta_pcm)} bytes)",
        )
        checar(
            worker.interrupcoes_na_chamada == 0,
            "nenhuma interrupção contabilizada com o recurso desligado",
        )
        checar(
            na_fila == 0,
            f"e a fila do microfone é limpa no fim, como sempre foi "
            f"({na_fila} blocos sobraram)",
        )

        modulo.CARENCIA_INTERRUPCAO_SEGUNDOS = 30.0
        worker.interrupcao_habilitada = True
        worker.interrupcoes_na_chamada = 0

        escritos, _sobra = _tocar(worker, resposta_pcm, blocos_fala)

        checar(
            worker.interrupcoes_na_chamada == 0
            and escritos == len(resposta_pcm),
            "durante a carência, nem a voz interrompe (é a cauda da "
            "própria frase do usuário)",
        )

        modulo.CARENCIA_INTERRUPCAO_SEGUNDOS = 0.02

        worker.interrupcoes_na_chamada = 0
        eco = _blocos_de(fala * 0.25)

        escritos, _sobra = _tocar(worker, resposta_pcm, eco)

        checar(
            worker.interrupcoes_na_chamada == 1,
            "a PRÓPRIA voz do assistente (eco a -12 dB) interrompe — "
            "é por isso que o recurso exige fone de ouvido",
        )

    finally:
        modulo.CARENCIA_INTERRUPCAO_SEGUNDOS = carencia_original
        modulo.ATRASO_REABRIR_MICROFONE = atraso_original
        worker.interrupcao_habilitada = False
        worker.interrupcoes_na_chamada = 0
        worker._blocos_apos_interrupcao = []
        worker.detector_fala = None
        worker.ativo = False

    fonte = Path(
        "jarvis/cerebro/voz_local/cliente_local.py"
    ).read_text(encoding="utf-8")

    checar(
        fonte.count(
            "self.alfred_falando and not self.interrupcao_habilitada"
        )
        == 2,
        "as 2 guardas de microfone do worker local têm a exceção de "
        f"interrupção (achei "
        f"{fonte.count('self.alfred_falando and not self.interrupcao_habilitada')})",
    )


def testar_mqtt_real(worker):
    titulo("5. Transporte MQTT contra o broker real (tópicos de teste)")

    originais = (
        config_local.TOPICO_ENTRADA,
        config_local.TOPICO_TEXTO_SAIDA,
        config_local.TOPICO_TEXTO_ENTRADA,
        config_local.TOPICO_SAIDA,
        config_local.TOPICO_ERRO,
    )

    config_local.TOPICO_ENTRADA = "jarvis/teste/audio/entrada"
    config_local.TOPICO_TEXTO_SAIDA = "jarvis/teste/texto/saida"
    config_local.TOPICO_TEXTO_ENTRADA = "jarvis/teste/texto/entrada"
    config_local.TOPICO_SAIDA = "jarvis/teste/audio/saida"
    config_local.TOPICO_ERRO = "jarvis/teste/erro"

    recebidos = []

    cliente = ClienteVozLocal(
        ao_receber_texto=lambda dados: recebidos.append(("texto", dados)),
        ao_receber_saida=lambda dados, texto=None: recebidos.append(
            ("audio", (dados, texto))
        ),
        ao_receber_erro=lambda texto: recebidos.append(("erro", texto)),
    )

    try:
        sucesso, mensagem = cliente.conectar()

        checar(sucesso, f"conecta no broker local ({mensagem})")

        if not sucesso:
            return

        wav = audio_wav.pcm_para_wav(b"\x00\x01" * 8000, 16000, 1)

        ok, msg = cliente.publicar_entrada(wav)

        checar(
            ok,
            f"ETAPA 1 publica o WAV em {config_local.TOPICO_ENTRADA} ({msg})",
        )

        transcricao = {"texto": "bom dia", "tom": "animado", "sexo": "M"}

        ok2, msg2 = cliente.publicar_texto(transcricao)

        checar(
            ok2,
            "ETAPA 2 publica o JSON em "
            f"{config_local.TOPICO_TEXTO_ENTRADA} ({msg2})",
        )

        cliente._cliente.publish(
            config_local.TOPICO_TEXTO_SAIDA,
            json.dumps(transcricao, ensure_ascii=False).encode("utf-8"),
            qos=1,
        )
        from paho.mqtt.packettypes import PacketTypes
        from paho.mqtt.properties import Properties

        props = Properties(PacketTypes.PUBLISH)
        props.UserProperty = [
            (config_local.PROPRIEDADE_TEXTO_RESPOSTA, TEXTO_DA_RESPOSTA)
        ]

        cliente._cliente.publish(
            config_local.TOPICO_SAIDA, wav, qos=1, properties=props
        )
        cliente._cliente.publish(
            config_local.TOPICO_ERRO,
            "transcrição: whisper falhou".encode("utf-8"),
            qos=1,
        )

        limite = time.time() + 5

        while time.time() < limite and len(recebidos) < 3:
            time.sleep(0.1)

        tipos = [tipo for tipo, _ in recebidos]

        checar("texto" in tipos, "callback do tópico de texto disparou")
        checar("audio" in tipos, "callback do tópico de saída disparou")
        checar("erro" in tipos, "callback do tópico de erro disparou")

        for tipo, conteudo in recebidos:
            if tipo == "audio":
                payload_audio, texto_propriedade = conteudo

                checar(
                    payload_audio == wav,
                    "o payload de áudio chegou íntegro (arquivo inteiro, "
                    "sem base64)",
                )

                checar(
                    texto_propriedade == TEXTO_DA_RESPOSTA,
                    f"e o texto da resposta veio na user property "
                    f"'{config_local.PROPRIEDADE_TEXTO_RESPOSTA}' "
                    f"({texto_propriedade!r})",
                )

            elif tipo == "texto":
                checar(
                    json.loads(conteudo.decode("utf-8")) == transcricao,
                    "o JSON da transcrição chegou íntegro",
                )

            else:
                checar(
                    conteudo == "transcrição: whisper falhou",
                    "o texto de erro chegou decodificado, com acento e "
                    f"prefixo da etapa ({conteudo!r})",
                )

        gigante = b"\x00" * (config_local.LIMITE_ENVIO_MB * 1024 * 1024 + 10)

        ok_grande, msg_grande = cliente.publicar_entrada(gigante)

        checar(
            not ok_grande and "grande" in msg_grande,
            f"áudio acima do limite é recusado ({msg_grande})",
        )

    finally:
        cliente.desconectar()

        (
            config_local.TOPICO_ENTRADA,
            config_local.TOPICO_TEXTO_SAIDA,
            config_local.TOPICO_TEXTO_ENTRADA,
            config_local.TOPICO_SAIDA,
            config_local.TOPICO_ERRO,
        ) = originais

    host_original = config_local.VOZ_LOCAL_MQTT_HOST
    porta_original = config_local.VOZ_LOCAL_MQTT_PORT

    config_local.VOZ_LOCAL_MQTT_PORT = 1

    try:
        cliente_morto = ClienteVozLocal(
            ao_receber_texto=lambda dados: None,
            ao_receber_saida=lambda dados: None,
            ao_receber_erro=lambda texto: None,
        )

        inicio = time.time()
        sucesso, mensagem = cliente_morto.conectar()
        gasto = time.time() - inicio

        checar(
            not sucesso and gasto < config_local.TIMEOUT_CONEXAO_SEGUNDOS + 2,
            f"broker fora do ar falha rápido e por escrito ({gasto:.1f}s): "
            f"{mensagem}",
        )

    finally:
        config_local.VOZ_LOCAL_MQTT_HOST = host_original
        config_local.VOZ_LOCAL_MQTT_PORT = porta_original


def testar_fluxo_worker(worker):
    titulo("6. Fluxo de turno em duas etapas (transcricao -> resposta)")

    wav = audio_wav.pcm_para_wav(b"\x00\x01" * 8000, 16000, 1)
    pcm_frase = b"\x00\x01" * 16000
    transcricao = {"texto": "que horas sao", "tom": "neutro", "sexo": "M"}

    class ClienteFalso:
        def __init__(self, resposta_etapa1=None, resposta_etapa2=None,
                     atraso=0.05, publica=True):
            self.resposta_etapa1 = resposta_etapa1
            self.resposta_etapa2 = resposta_etapa2
            self.atraso = atraso
            self.publica = publica
            self.audios_publicados = []
            self.textos_publicados = []

        def _responder(self, resposta):
            if resposta is None:
                return

            def tarefa():
                time.sleep(self.atraso)
                worker._entregar_resposta(resposta)

            import threading

            threading.Thread(target=tarefa, daemon=True).start()

        def publicar_entrada(self, dados):
            self.audios_publicados.append(dados)

            if not self.publica:
                return (False, "O broker nao confirmou o envio do audio.")

            self._responder(self.resposta_etapa1)

            return (True, "enviado")

        def publicar_texto(self, dados):
            self.textos_publicados.append(dados)

            if not self.publica:
                return (False, "O broker nao confirmou o envio do texto.")

            self._responder(self.resposta_etapa2)

            return (True, "enviado")

    def rodar(cliente, corrotina):
        async def principal():
            worker.ativo = True
            worker.loop = asyncio.get_running_loop()
            worker.cliente_mqtt = cliente

            try:
                return await corrotina()

            finally:
                worker.loop = None
                worker.cliente_mqtt = None

        return asyncio.run(principal())

    cliente = ClienteFalso(resposta_etapa1=("texto", transcricao))

    resultado = rodar(cliente, lambda: worker._transcrever(pcm_frase))

    checar(
        resultado == ("texto", transcricao),
        "ETAPA 1 devolve o JSON da transcricao",
    )

    checar(
        len(cliente.audios_publicados) == 1
        and cliente.audios_publicados[0][:4] == b"RIFF",
        "o que vai para jarvis/audio/entrada e um WAV, nao PCM cru",
    )

    checar(
        not cliente.textos_publicados,
        "a ETAPA 2 NAO e chamada junto (sao duas chamadas separadas)",
    )

    import jarvis.cerebro.voz_local.cliente_local as modulo_local

    resposta_falada = modulo_local.RespostaFalada(wav, TEXTO_DA_RESPOSTA)
    cliente = ClienteFalso(resposta_etapa2=("audio", resposta_falada))

    resultado = rodar(cliente, lambda: worker._pedir_resposta(transcricao))

    checar(
        resultado == ("audio", resposta_falada)
        and resultado[1].audio == wav,
        "ETAPA 2 devolve o WAV da resposta falada",
    )

    checar(
        resultado[1].texto == TEXTO_DA_RESPOSTA,
        "e o texto que ele fala vem junto, no mesmo resultado",
    )

    publicado = cliente.textos_publicados[0]

    checar(
        all(publicado.get(k) == v for k, v in transcricao.items()),
        "a ETAPA 2 republica os campos da etapa 1 sem alterar nenhum "
        "(tom e sexo incluídos, sem remontar campo a campo)",
    )

    checar(
        set(publicado) - set(transcricao) <= {"historico", "contexto_sistema"},
        f"e o que se acrescenta são só os campos de memória "
        f"({sorted(set(publicado) - set(transcricao))})",
    )

    for rotulo, resposta, corrotina in (
        (
            "transcricao",
            ("erro", "transcricao: whisper falhou"),
            lambda: worker._transcrever(pcm_frase),
        ),
        (
            "resposta",
            ("erro", "resposta: tts falhou"),
            lambda: worker._pedir_resposta(transcricao),
        ),
    ):
        cliente = ClienteFalso(
            resposta_etapa1=resposta,
            resposta_etapa2=resposta,
        )

        obtido = rodar(cliente, corrotina)

        checar(
            obtido is not None and obtido[0] == "erro",
            f"erro publicado durante a etapa de {rotulo} vira erro do turno",
        )

    t_orig = (
        config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS,
        config_local.TIMEOUT_RESPOSTA_SEGUNDOS,
    )

    config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS = 1
    config_local.TIMEOUT_RESPOSTA_SEGUNDOS = 1

    try:
        for rotulo, corrotina, topico in (
            (
                "transcricao",
                lambda: worker._transcrever(pcm_frase),
                config_local.TOPICO_TEXTO_SAIDA,
            ),
            (
                "resposta",
                lambda: worker._pedir_resposta(transcricao),
                config_local.TOPICO_SAIDA,
            ),
        ):
            inicio = time.time()
            obtido = rodar(ClienteFalso(), corrotina)
            gasto = time.time() - inicio

            checar(
                obtido is not None
                and obtido[0] == "erro"
                and "nenhuma resposta" in obtido[1]
                and topico in obtido[1],
                f"servidor mudo na etapa de {rotulo} vira timeout tratado, "
                "nomeando o topico certo",
            )

            checar(
                gasto < 3,
                f"o timeout da etapa de {rotulo} desiste em ~1s ({gasto:.1f}s)",
            )

            checar(
                worker._futuro_resposta is None
                and worker._tipo_esperado is None,
                f"o future da etapa de {rotulo} e liberado no timeout",
            )

    finally:
        (
            config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS,
            config_local.TIMEOUT_RESPOSTA_SEGUNDOS,
        ) = t_orig

    checar(
        rodar(
            ClienteFalso(publica=False),
            lambda: worker._transcrever(pcm_frase),
        )[0] == "erro",
        "falha ao publicar vira erro do turno, nao excecao",
    )

    config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS = 2

    try:
        cliente = ClienteFalso(resposta_etapa1=("audio", wav))

        inicio = time.time()
        obtido = rodar(cliente, lambda: worker._transcrever(pcm_frase))
        gasto = time.time() - inicio

        checar(
            obtido is not None
            and obtido[0] == "erro"
            and "nenhuma resposta" in obtido[1],
            "audio chegando enquanto a etapa 1 espera texto e DESCARTADO "
            "(vira timeout, nao e aceito como transcricao)",
        )

        checar(gasto >= 1.5, f"e a espera seguiu ate o timeout ({gasto:.1f}s)")

    finally:
        config_local.TIMEOUT_TRANSCRICAO_SEGUNDOS = t_orig[0]

    coletados = []
    original = worker._entregar_resposta
    worker._entregar_resposta = coletados.append

    try:
        worker._ao_receber_texto_mqtt(b"{isso nao e json")

        checar(
            coletados
            and coletados[0][0] == "erro"
            and "ileg" in coletados[0][1],
            "JSON quebrado na etapa 1 vira erro do turno, nao excecao",
        )

        coletados.clear()
        worker._ao_receber_texto_mqtt(b'["lista", "em vez de objeto"]')

        checar(
            coletados and coletados[0][0] == "erro",
            "JSON valido mas que nao e objeto tambem e recusado",
        )

        coletados.clear()
        acentuado = {"texto": "bom dia, tudo bem?", "tom": "animado", "sexo": "F"}
        worker._ao_receber_texto_mqtt(
            json.dumps(acentuado, ensure_ascii=False).encode("utf-8")
        )

        checar(
            coletados == [("texto", acentuado)],
            "JSON valido em UTF-8 e decodificado com acentos preservados",
        )

    finally:
        worker._entregar_resposta = original

    erros = []
    worker.erro_recebido.connect(erros.append)

    worker.loop = None
    worker._futuro_resposta = None
    worker._tipo_esperado = None

    worker._resolver_futuro(("audio", wav))
    worker._resolver_futuro(("texto", transcricao))

    checar(
        len(erros) == 0,
        "audio e texto fora de hora sao descartados em silencio",
    )

    worker._resolver_futuro(("erro", "resposta: etapa X falhou"))

    checar(
        len(erros) == 1 and "etapa X falhou" in erros[0],
        "erro fora de hora ainda aparece na interface",
    )

    worker.erro_recebido.disconnect(erros.append)


def testar_roteamento(worker):
    titulo("6b. Roteamento entre as duas etapas")

    import jarvis.cerebro.voz_local.cliente_local as modulo

    class DecisaoFalsa:
        def __init__(self, resposta, usou_ferramenta=False,
                     ferramenta_executada=None, pedido_esclarecimento=False):
            self.resposta = resposta
            self.usou_ferramenta = usou_ferramenta
            self.ferramenta_executada = ferramenta_executada
            self.pedido_esclarecimento = pedido_esclarecimento

    class RoteamentoFalso:
        def __init__(self, decisao=None, erro=None):
            self.decisao = decisao
            self.erro = erro
            self.chamadas = []
            self.ganchos = []

        def processar_turno(
            self,
            mensagem,
            historico=None,
            preparar_argumentos=None,
        ):
            self.chamadas.append((mensagem, list(historico or [])))
            self.ganchos.append(preparar_argumentos)

            if self.erro:
                raise self.erro

            return self.decisao

    original = modulo.roteamento_hierarquico

    def rodar(falso, texto):
        modulo.roteamento_hierarquico = falso

        async def principal():
            worker.ativo = True
            worker.loop = asyncio.get_running_loop()

            try:
                return await worker._rotear(texto)

            finally:
                worker.loop = None

        try:
            return asyncio.run(principal())

        finally:
            modulo.roteamento_hierarquico = original

    falso = RoteamentoFalso(
        DecisaoFalsa(
            "Cancelei o evento.",
            usou_ferramenta=True,
            ferramenta_executada="cancelar_evento_agenda",
        )
    )

    decisao = rodar(falso, "cancela meu evento de amanha")

    checar(
        decisao is not None and decisao.usou_ferramenta,
        "o roteamento e consultado com o texto transcrito",
    )

    checar(
        falso.chamadas
        and falso.chamadas[0][0] == "cancela meu evento de amanha",
        "o texto vai ao roteamento exatamente como transcrito",
    )

    checar(
        falso.ganchos
        and falso.ganchos[0] == worker._preparar_argumentos_da_ferramenta,
        "e o gancho de captura de imagem é repassado ao roteamento",
    )

    falso_conversa = RoteamentoFalso(DecisaoFalsa("", usou_ferramenta=False))

    decisao = rodar(falso_conversa, "bom dia")

    checar(
        decisao is not None and not decisao.usou_ferramenta,
        "conversa e reconhecida como conversa",
    )

    erros = []
    worker.erro_recebido.connect(erros.append)

    try:
        decisao = rodar(
            RoteamentoFalso(erro=RuntimeError("groq fora do ar")),
            "qualquer coisa",
        )

        checar(
            decisao is None,
            "falha no roteamento devolve None (o turno segue como conversa)",
        )

        checar(
            len(erros) == 1 and "roteamento" in erros[0].lower(),
            "e a falha aparece na interface em vez de sumir",
        )

    finally:
        worker.erro_recebido.disconnect(erros.append)

    worker.transcricao_conversa = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "ola"},
        {"role": "user", "content": "que horas sao"},
    ]

    falso_hist = RoteamentoFalso(DecisaoFalsa(""))
    rodar(falso_hist, "que horas sao")

    checar(
        falso_hist.chamadas
        and falso_hist.chamadas[0][1]
        == [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "ola"},
        ],
        "o historico vai sem a fala atual (senao ela iria duplicada)",
    )

    worker.transcricao_conversa = []
    status = []
    worker.status_recebido.connect(status.append)

    try:
        worker._registrar_resultado_local(
            DecisaoFalsa(
                "Evento cancelado.",
                usou_ferramenta=True,
                ferramenta_executada="cancelar_evento_agenda",
            )
        )

        checar(
            status == ["Evento cancelado."],
            "turno resolvido por ferramenta mostra o resultado na interface",
        )

        checar(
            worker.transcricao_conversa
            == [{"role": "assistant", "content": "Evento cancelado."}],
            "e entra no historico, para o proximo turno ter contexto",
        )

    finally:
        worker.status_recebido.disconnect(status.append)

    worker.transcricao_conversa = [
        {"role": "user", "content": str(i)}
        for i in range(modulo.MAXIMO_MENSAGENS_TRANSCRICAO + 5)
    ]

    worker._aparar_transcricao()

    checar(
        len(worker.transcricao_conversa) == modulo.MAXIMO_MENSAGENS_TRANSCRICAO,
        f"o historico e aparado em {modulo.MAXIMO_MENSAGENS_TRANSCRICAO} "
        "mensagens (vai inteiro ao roteamento a cada turno)",
    )

    checar(
        worker.transcricao_conversa[-1]["content"]
        == str(modulo.MAXIMO_MENSAGENS_TRANSCRICAO + 4),
        "e o que sobra sao as mensagens mais RECENTES",
    )

    worker.transcricao_conversa = []


def testar_falha_de_roteamento(worker):
    titulo("6c. Falha de roteamento não pode virar conversa")

    from jarvis.roteamento_hierarquico.roteador import ResultadoTurno

    checar(
        ResultadoTurno("x").falhou is False,
        "ResultadoTurno tem .falhou, e o padrão é False",
    )

    checar(
        ResultadoTurno("x", falhou=True).falhou is True,
        "e pode ser marcado como falha",
    )

    falha = ResultadoTurno("Limite de uso da Groq atingido", falhou=True)
    conversa = ResultadoTurno("", usou_ferramenta=False)

    checar(
        falha.usou_ferramenta == conversa.usou_ferramenta
        and falha.falhou != conversa.falhou,
        "falha e conversa só se distinguem por .falhou "
        "(usou_ferramenta é False nos dois)",
    )

    import jarvis.cerebro.voz_local.cliente_local as modulo

    chamadas = {"transcrever": 0, "responder": 0}

    async def transcrever_falso(pcm):
        chamadas["transcrever"] += 1

        return ("texto", {"texto": "abre o navegador", "tom": "n", "sexo": "M"})

    async def pedir_resposta_falso(dados):
        chamadas["responder"] += 1

        return ("audio", modulo.RespostaFalada(b"", None))

    async def capturar_falso(fila):
        if chamadas["transcrever"] == 0:
            return b"\x00\x01" * 16000

        worker.ativo = False

        return None

    async def reproduzir_falso(*args, **kwargs):
        return None

    def rodar(decisao):
        async def rotear_falso(texto):
            return decisao

        originais = (
            worker._transcrever,
            worker._pedir_resposta,
            worker._capturar_frase,
            worker._reproduzir_resposta,
            worker._rotear,
        )

        worker._transcrever = transcrever_falso
        worker._pedir_resposta = pedir_resposta_falso
        worker._capturar_frase = capturar_falso
        worker._reproduzir_resposta = reproduzir_falso
        worker._rotear = rotear_falso

        chamadas["transcrever"] = 0
        chamadas["responder"] = 0

        async def principal():
            worker.ativo = True
            worker.loop = asyncio.get_running_loop()
            worker.transcricao_conversa = []

            try:
                await asyncio.wait_for(
                    worker.ciclo_de_conversa(asyncio.Queue(), None),
                    timeout=10,
                )

            finally:
                worker.loop = None

        try:
            asyncio.run(principal())

        finally:
            (
                worker._transcrever,
                worker._pedir_resposta,
                worker._capturar_frase,
                worker._reproduzir_resposta,
                worker._rotear,
            ) = originais

    erros = []
    worker.erro_recebido.connect(erros.append)

    try:
        rodar(ResultadoTurno("Limite de uso da Groq atingido", falhou=True))

        checar(
            chamadas["responder"] == 0,
            "roteamento falhou -> a etapa 2 NÃO é chamada "
            "(o servidor não inventa que executou)",
        )

        checar(
            any("não consegui decidir" in e.lower() for e in erros),
            f"e a falha aparece na interface ({erros})",
        )

        erros.clear()
        rodar(ResultadoTurno("", usou_ferramenta=False))

        checar(
            chamadas["responder"] == 1,
            "conversa de verdade -> a etapa 2 SEGUE sendo chamada",
        )

        checar(
            not erros,
            "e sem erro nenhum na interface",
        )

        erros.clear()
        rodar(
            ResultadoTurno(
                "Abri o navegador.",
                usou_ferramenta=True,
                ferramenta_executada="abrir_aplicativo",
            )
        )

        checar(
            chamadas["responder"] == 0,
            "ferramenta -> a etapa 2 segue não sendo chamada",
        )

    finally:
        worker.erro_recebido.disconnect(erros.append)

    worker.transcricao_conversa = []


def testar_retry_groq():
    titulo("6d. Retry no limite da Groq e preservação do motivo do erro")

    from types import SimpleNamespace

    from langchain_core.messages import AIMessage

    from jarvis.roteamento_hierarquico import config as config_rot
    from jarvis.roteamento_hierarquico import roteador
    from jarvis.servicos import agentes
    from jarvis.servicos.agentes import agente as motor

    class ErroFalso(Exception):
        def __init__(self, status, mensagem, headers=None):
            super().__init__(mensagem)
            self.response = SimpleNamespace(
                status_code=status,
                headers=headers or {},
            )

    MENSAGEM_429 = (
        "Rate limit reached for model `openai/gpt-oss-20b` ... "
        "on tokens per minute (TPM): Limit 8000, Used 6406. "
        "Please try again in 975ms."
    )

    erro_429 = ErroFalso(429, MENSAGEM_429)

    detalhe = agentes.erros.descrever(erro_429)

    checar(
        "tokens per minute" in detalhe and "8000" in detalhe,
        f"o motivo do erro da Groq é preservado ({detalhe[:60]}...)",
    )

    checar(
        agentes.erros.classificar(erro_429) == agentes.erros.LIMITE,
        "e um 429 é classificado como limite de uso",
    )

    checar(
        agentes.erros.classificar(ErroFalso(401, "invalid_api_key"))
        == agentes.erros.AUTENTICACAO,
        "enquanto um 401 é classificado como autenticação",
    )

    def espera(erro, tentativa):
        return agentes.erros.espera_sugerida(
            erro,
            tentativa,
            config_rot.ESPERA_BASE_RATE_LIMIT,
            config_rot.ESPERA_MAXIMA_RATE_LIMIT,
        )

    checar(
        espera(ErroFalso(429, MENSAGEM_429, {"retry-after": "1"}), 0) == 1.0,
        "o retry-after do servidor é respeitado",
    )

    checar(
        espera(ErroFalso(429, MENSAGEM_429, {"retry-after": "999"}), 0)
        == config_rot.ESPERA_MAXIMA_RATE_LIMIT,
        f"e limitado a {config_rot.ESPERA_MAXIMA_RATE_LIMIT}s "
        "(o valor vem de fora)",
    )

    checar(
        abs(espera(erro_429, 0) - 0.975) < 0.001,
        f'o "try again in 975ms" da mensagem é lido ({espera(erro_429, 0)})',
    )

    esperas = [
        espera(ErroFalso(429, "Rate limit reached"), tentativa)
        for tentativa in range(3)
    ]

    checar(
        esperas[0] < esperas[1] <= config_rot.ESPERA_MAXIMA_RATE_LIMIT,
        f"sem nenhum dos dois, o backoff cresce {esperas}",
    )

    class ModeloFalso:
        def __init__(self, sequencia, registro):
            self.sequencia = sequencia
            self.registro = registro

        def bind_tools(self, *args, **kwargs):
            return self

        def bind(self, *args, **kwargs):
            return self

        def invoke(self, mensagens):
            self.registro["chamadas"] += 1
            self.registro["papeis"].append(
                [type(m).__name__ for m in mensagens]
            )

            indice = min(
                self.registro["chamadas"] - 1, len(self.sequencia) - 1
            )
            item = self.sequencia[indice]

            if isinstance(item, Exception):
                raise item

            return item

    def rodar(sequencia, historico=None):
        registro = {"chamadas": 0, "dormidas": [], "papeis": []}

        criar_original = motor.modelos.criar_modelo
        sleep_original = motor.time.sleep

        motor.modelos.criar_modelo = (
            lambda *a, **k: ModeloFalso(sequencia, registro)
        )
        motor.time.sleep = registro["dormidas"].append

        try:
            resposta = roteador._consultar(
                roteador._pedido_groq(
                    "instrução de sistema",
                    "uma frase qualquer",
                    "modelo-de-teste",
                    historico=historico,
                )
            )

        finally:
            motor.modelos.criar_modelo = criar_original
            motor.time.sleep = sleep_original

        return resposta, registro

    resposta, registro = rodar(
        [erro_429, erro_429, AIMessage(content="deu certo")]
    )

    checar(
        resposta.sucesso and registro["chamadas"] == 3,
        f"429 é repetido até dar certo ({registro['chamadas']} tentativas)",
    )

    checar(
        len(registro["dormidas"]) == 2,
        f"e esperou entre as tentativas ({registro['dormidas']})",
    )

    resposta, registro = rodar([erro_429])

    checar(
        not resposta.sucesso and "tokens per minute" in resposta.erro,
        "esgotadas as tentativas, o motivo real chega a quem chamou",
    )

    checar(
        registro["chamadas"] == config_rot.TENTATIVAS_RATE_LIMIT,
        f"gastando o orçamento inteiro ({registro['chamadas']} de "
        f"{config_rot.TENTATIVAS_RATE_LIMIT})",
    )

    checar(
        len(registro["dormidas"]) == config_rot.TENTATIVAS_RATE_LIMIT - 1,
        "e não dorme depois da última tentativa "
        f"({len(registro['dormidas'])} esperas para "
        f"{config_rot.TENTATIVAS_RATE_LIMIT} tentativas)",
    )

    resposta, registro = rodar([ErroFalso(400, "modelo invalido")])

    checar(
        not resposta.sucesso and registro["chamadas"] == 1,
        f"erro que não é 429 volta na primeira tentativa "
        f"({registro['chamadas']} chamada)",
    )

    checar(
        "modelo invalido" in resposta.erro,
        f"com o motivo junto ({resposta.erro})",
    )

    _, registro = rodar(
        [AIMessage(content="ok")],
        historico=[{"role": "assistant", "content": "falei antes"}],
    )

    checar(
        registro["papeis"]
        and registro["papeis"][0]
        == ["SystemMessage", "AIMessage", "HumanMessage"],
        f"sistema + histórico + usuário, nessa ordem "
        f"({registro['papeis'][0] if registro['papeis'] else []})",
    )


def testar_captura_para_ferramentas_visuais(worker):
    titulo("6e. Captura de imagem para as ferramentas visuais")

    import jarvis.cerebro.voz_local.cliente_local as modulo

    usadas = []
    originais = dict(modulo._CAPTURAS)

    modulo._CAPTURAS = {
        origem: (lambda o=origem: (usadas.append(o) or f"JPEG-{o}".encode()))
        for origem in originais
    }

    try:
        for nome, origem in modulo.FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM.items():
            usadas.clear()

            args = worker._preparar_argumentos_da_ferramenta(nome, {"p": 1})

            checar(
                args.get("imagem_bytes") == f"JPEG-{origem}".encode(),
                f"{nome} recebe imagem_bytes capturado na hora",
            )

            checar(
                args.get("p") == 1 and len(usadas) == 1,
                "preservando os argumentos originais, com UMA captura",
            )

            checar(
                usadas == [origem],
                f"e a captura usada é a d{'a tela' if origem == 'tela' else 'a câmera'}",
            )

        checar(
            modulo.FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM["descrever_tela"] == "tela"
            and modulo.FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM["descrever_camera"]
            == "camera",
            "descrever_tela usa a tela e descrever_camera usa a câmera",
        )

        usadas.clear()
        entrada_comum = {"nome": "navegador"}
        args = worker._preparar_argumentos_da_ferramenta(
            "abrir_aplicativo", entrada_comum
        )

        checar(
            not usadas and "imagem_bytes" not in args,
            "uma ferramenta comum NÃO captura nada",
        )

        checar(
            args is entrada_comum,
            "e nem sequer copia o dicionário à toa",
        )

        entrada = {"pergunta": "o que é isso"}
        worker._preparar_argumentos_da_ferramenta(
            "consultar_segunda_opiniao_visual", entrada
        )

        checar(
            "imagem_bytes" not in entrada,
            "o dicionário do roteamento não é modificado no lugar",
        )

    finally:
        modulo._CAPTURAS = originais

    import inspect

    from jarvis.roteamento_hierarquico.roteador import processar_turno

    checar(
        "preparar_argumentos" in inspect.signature(processar_turno).parameters,
        "processar_turno aceita o gancho preparar_argumentos",
    )


def testar_visao_portada():
    titulo("6f. Visão portada: descrever_tela e descrever_camera")

    from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS
    from jarvis.pacotes import descricao_visual
    from jarvis.pacotes.descricao_visual import cliente_visao
    from jarvis.pacotes.descricao_visual import config as config_visao
    from jarvis.roteamento_hierarquico import catalogo

    nomes = [d.name for d in descricao_visual.obter_function_declarations()]

    checar(
        sorted(nomes) == ["descrever_camera", "descrever_tela"],
        f"o pacote declara as duas ferramentas ({nomes})",
    )

    checar(
        descricao_visual.despachar("ferramenta_inexistente", {}) is None,
        "despachar devolve None para nome desconhecido (contrato do projeto)",
    )

    checar(
        descricao_visual in PACOTES_REGISTRADOS,
        "e o pacote está em PACOTES_REGISTRADOS",
    )

    nativas_do_gemini = {"analisar_tela", "analisar_camera"}

    todos_de_pacote = {
        d.name
        for pacote in PACOTES_REGISTRADOS
        for d in pacote.obter_function_declarations()
    }

    checar(
        not (nativas_do_gemini & todos_de_pacote),
        "nenhum pacote usa os nomes nativos do Gemini "
        "(senão o despacho do Gemini seria sequestrado)",
    )

    for nome in ("descrever_tela", "descrever_camera"):
        checar(
            nome in catalogo.CATALOGO_CURTO,
            f"{nome} está no catálogo do roteamento (senão é inalcançável)",
        )

        checar(
            catalogo.CATALOGO_CURTO[nome][0] == "visao_camera",
            f"{nome} na categoria visao_camera",
        )

    checar(
        catalogo.verificar_catalogo_atualizado(PACOTES_REGISTRADOS),
        "catálogo e pacotes registrados seguem coerentes",
    )

    from jarvis.nucleo.perfis import sensiveis

    checar(
        sensiveis.e_sensivel("descrever_tela")
        and sensiveis.e_sensivel("descrever_camera"),
        "as duas são sensíveis (veem a tela/câmera e mandam para fora)",
    )

    original = cliente_visao.descrever
    chamadas = []

    def descrever_falso(imagem_bytes, pergunta, origem):
        chamadas.append((len(imagem_bytes or b""), pergunta, origem))

        return True, f"Descrição da {origem}."

    cliente_visao.descrever = descrever_falso

    try:
        texto = descricao_visual.despachar(
            "descrever_tela",
            {"imagem_bytes": b"JPEG" * 10, "pergunta": "que erro é esse?"},
        )

        checar(
            texto == "Descrição da tela.",
            "descrever_tela devolve a descrição pronta para falar",
        )

        checar(
            chamadas[-1] == (40, "que erro é esse?", "tela"),
            f"repassando imagem, pergunta e origem corretas ({chamadas[-1]})",
        )

        descricao_visual.despachar(
            "descrever_camera", {"imagem_bytes": b"JPEG"}
        )

        checar(
            chamadas[-1][2] == "câmera",
            "descrever_camera identifica a origem como câmera",
        )

    finally:
        cliente_visao.descrever = original

    texto = descricao_visual.despachar("descrever_tela", {})

    checar(
        "não consegui ver a tela" in texto.lower()
        and "nenhuma imagem" in texto.lower(),
        f"sem imagem, explica em vez de estourar ({texto})",
    )

    chave_original = config_visao.GEMINI_API_KEY
    provedor_original = config_visao.provedor_visao

    try:
        config_visao.provedor_visao = lambda: "gemini"
        config_visao.GEMINI_API_KEY = None

        texto = descricao_visual.despachar(
            "descrever_camera", {"imagem_bytes": b"JPEG"}
        )

        checar(
            "gemini_api_key" in texto.lower(),
            f"sem chave, diz qual chave falta ({texto})",
        )

        config_visao.provedor_visao = lambda: "mistral"
        chave_mistral = config_visao.MISTRAL_API_KEY
        config_visao.MISTRAL_API_KEY = None

        try:
            texto = descricao_visual.despachar(
                "descrever_camera", {"imagem_bytes": b"JPEG"}
            )

            checar(
                "mistral_api_key" in texto.lower(),
                f"com provedor=mistral, vai pelo caminho da Mistral ({texto})",
            )

        finally:
            config_visao.MISTRAL_API_KEY = chave_mistral

    finally:
        config_visao.GEMINI_API_KEY = chave_original
        config_visao.provedor_visao = provedor_original

    caminho_original = config_visao.CAMINHO_ENV
    env_falso = Path(tempfile.mkdtemp(prefix="jarvis_env_")) / ".env"

    ambiente_original = os.environ.pop("DESCRICAO_VISUAL_PROVEDOR", None)

    try:
        for valor_bruto, esperado, descricao in (
            ("", "gemini", "sem a variável no .env"),
            (
                "DESCRICAO_VISUAL_PROVEDOR=provedor_que_nao_existe",
                "gemini",
                "com valor inválido (erro de digitação)",
            ),
            (
                "DESCRICAO_VISUAL_PROVEDOR=mistral",
                "mistral",
                "com a escolha manual do usuário",
            ),
        ):
            env_falso.write_text(valor_bruto, encoding="utf-8")
            config_visao.CAMINHO_ENV = env_falso

            checar(
                config_visao.provedor_visao() == esperado,
                f"descricao_visual {descricao}: {esperado}",
            )

    finally:
        config_visao.CAMINHO_ENV = caminho_original

        if ambiente_original is not None:
            os.environ["DESCRICAO_VISUAL_PROVEDOR"] = ambiente_original


def testar_segunda_opiniao_provedor():
    titulo("6g. Segunda opinião visual: seletor de provedor")

    from jarvis.pacotes import identificacao_visual
    from jarvis.pacotes.identificacao_visual import config as config_2op
    from jarvis.pacotes.identificacao_visual import gemini_vision_client
    from jarvis.pacotes.identificacao_visual import mistral_vision_client
    from jarvis.pacotes.descricao_visual import config as config_desc

    caminho_original_2op = config_2op.CAMINHO_ENV
    caminho_original_desc = config_desc.CAMINHO_ENV
    provedor_ativo_original = nucleo_config.provedor_ativo

    env_falso = Path(tempfile.mkdtemp(prefix="jarvis_env_")) / ".env"
    env_falso.write_text("", encoding="utf-8")

    ambiente_original = os.environ.pop("DESCRICAO_VISUAL_PROVEDOR", None)

    try:
        config_2op.CAMINHO_ENV = env_falso
        config_desc.CAMINHO_ENV = env_falso

        for cerebro, esperado in (
            ("gemini", "mistral"),
            ("openai", "gemini"),
            ("local", "gemini"),
        ):
            nucleo_config.provedor_ativo = lambda c=cerebro: c

            checar(
                config_2op.provedor_visao() == esperado,
                f"cérebro de voz {cerebro} -> segunda opinião no "
                f"{esperado} (nunca o mesmo modelo que respondeu)",
            )

            checar(
                config_desc.provedor_visao() == "gemini",
                f"cérebro {cerebro}: descricao_visual segue no gemini "
                f"(assimetria proposital, ver os config.py)",
            )

        nucleo_config.provedor_ativo = lambda: "gemini"

        for forcado in ("gemini", "mistral"):
            env_falso.write_text(
                f"DESCRICAO_VISUAL_PROVEDOR={forcado}", encoding="utf-8"
            )

            checar(
                config_2op.provedor_visao() == forcado
                and config_desc.provedor_visao() == forcado,
                f"DESCRICAO_VISUAL_PROVEDOR={forcado} sobrepõe a regra "
                f"nos dois pacotes",
            )

        env_falso.write_text(
            "DESCRICAO_VISUAL_PROVEDOR=provedor_que_nao_existe",
            encoding="utf-8",
        )

        checar(
            config_2op.provedor_visao() == "mistral",
            "valor inválido cai na regra automática (cérebro gemini "
            "-> mistral), nunca num provedor sorteado",
        )

    finally:
        config_2op.CAMINHO_ENV = caminho_original_2op
        config_desc.CAMINHO_ENV = caminho_original_desc
        nucleo_config.provedor_ativo = provedor_ativo_original

        if ambiente_original is not None:
            os.environ["DESCRICAO_VISUAL_PROVEDOR"] = ambiente_original

    checar(
        sorted(identificacao_visual._CLIENTES) == ["gemini", "mistral"],
        "os dois provedores estão disponíveis",
    )

    checar(
        gemini_vision_client.NOME_PROVEDOR == "Gemini"
        and mistral_vision_client.NOME_PROVEDOR == "Mistral",
        "cada cliente expõe o próprio nome de provedor",
    )

    chamados = []

    class ClienteFalso:
        def __init__(self, nome):
            self.NOME_PROVEDOR = nome

        def consultar(self, imagem_bytes, pergunta):
            chamados.append(self.NOME_PROVEDOR)

            return True, f"resposta de {self.NOME_PROVEDOR}"

    originais = dict(identificacao_visual._CLIENTES)
    provedor_original = config_2op.provedor_visao

    identificacao_visual._CLIENTES = {
        "gemini": ClienteFalso("Gemini"),
        "mistral": ClienteFalso("Mistral"),
    }

    try:
        for provedor, esperado in (("gemini", "Gemini"), ("mistral", "Mistral")):
            chamados.clear()
            config_2op.provedor_visao = lambda p=provedor: p

            texto = identificacao_visual.despachar(
                "consultar_segunda_opiniao_visual",
                {"imagem_bytes": b"JPEG", "pergunta": "que objeto é esse?"},
            )

            checar(
                chamados == [esperado],
                f'PROVEDOR="{provedor}" consulta o cliente {esperado}',
            )

            checar(
                f"({esperado})" in texto,
                f"e a resposta nomeia quem respondeu ({texto[:60]}...)",
            )

        chamados.clear()
        config_2op.provedor_visao = lambda: "provedor_inexistente"

        identificacao_visual.despachar(
            "consultar_segunda_opiniao_visual",
            {"imagem_bytes": b"JPEG", "pergunta": "x"},
        )

        checar(
            chamados == ["Gemini"],
            "provedor desconhecido cai no Gemini em vez de estourar",
        )

    finally:
        identificacao_visual._CLIENTES = originais
        config_2op.provedor_visao = provedor_original

    texto = identificacao_visual.despachar(
        "consultar_segunda_opiniao_visual", {"pergunta": "o que é isso"}
    )

    checar(
        "própria visão" in texto and "segunda fonte" in texto,
        "sem imagem, mantém a instrução de responder com a própria visão",
    )

    nome_esperado = identificacao_visual._CLIENTES[
        config_2op.provedor_visao()
    ].NOME_PROVEDOR

    checar(
        nome_esperado in texto,
        f"e nomeia o provedor que falhou ({texto[:70]}...)",
    )

    from jarvis.nucleo import prompts

    checar(
        "{provedor}" in prompts.VISAO_INDISPONIVEL,
        "o texto de indisponibilidade é parametrizado pelo provedor",
    )

    checar(
        "Mistral" not in prompts.VISAO_INDISPONIVEL,
        "e não cita mais a Mistral como fonte fixa",
    )

    campos = {c["nome"]: c for c in config_2op.config_schema()}

    checar(
        campos["MISTRAL_API_KEY"]["obrigatoria"] is False,
        "MISTRAL_API_KEY não é mais obrigatória na tela de configurações",
    )

    checar(
        "IDENTIFICACAO_VISUAL_MODELO_GEMINI" in campos,
        "e o modelo do Gemini é configurável",
    )


def testar_memoria_local(worker):
    titulo("6h. Memória do modo local: histórico e fatos")

    from jarvis.cerebro.voz_local import contexto

    checar(
        contexto.historico_para_envio([]) == [],
        "histórico vazio não vira campo nenhum",
    )

    conversa = [
        {"role": "user", "content": f"mensagem {i}"}
        for i in range(contexto.LIMITE_MENSAGENS_HISTORICO + 4)
    ]

    enviado = contexto.historico_para_envio(conversa)

    checar(
        len(enviado) == contexto.LIMITE_MENSAGENS_HISTORICO,
        f"o histórico é cortado em {contexto.LIMITE_MENSAGENS_HISTORICO} "
        f"mensagens ({len(enviado)})",
    )

    checar(
        enviado[-1]["content"] == conversa[-1]["content"],
        "e o que sobra são as mensagens mais RECENTES",
    )

    original = [{"role": "user", "content": "oi"}]
    copia = contexto.historico_para_envio(original)
    copia[0]["content"] = "alterado"

    checar(
        original[0]["content"] == "oi",
        "devolve cópia — alterar o enviado não mexe na transcrição viva",
    )

    checar(
        contexto.historico_para_envio(
            [{"role": "user", "content": "   "}]
        )
        == [],
        "mensagem vazia não é enviada",
    )

    texto = contexto.montar_contexto_sistema("qual é o meu nome?")

    checar(
        bool(texto) and "assistente pessoal" in texto,
        "o contexto traz a identidade do assistente",
    )

    checar(
        "Data e hora" in texto,
        "e a data/hora atual (mesmo dado que os outros dois cérebros recebem)",
    )

    from jarvis.pacotes.memoria_obsidian import config as config_memoria

    if config_memoria.configurado():
        checar(
            "Fatos que você já sabe" in texto,
            "com o vault configurado, fatos relevantes entram no contexto",
        )

        neutro = contexto.montar_contexto_sistema("bom dia, tudo bem?")

        checar(
            "Fatos que você já sabe" not in neutro,
            "e uma fala sem assunto NÃO arrasta memória irrelevante",
        )

    else:
        print("       (vault não configurado — parte de fatos pulada)")

    checar(
        contexto.montar_contexto_sistema("") != "",
        "sem fala, ainda assim devolve identidade e data",
    )

    limite_original = contexto.LIMITE_CONTEXTO_CARACTERES
    contexto.LIMITE_CONTEXTO_CARACTERES = 80

    try:
        curto = contexto.montar_contexto_sistema("qual é o meu nome?")

        checar(
            len(curto) <= 83,
            f"o contexto respeita o teto de caracteres ({len(curto)})",
        )

    finally:
        contexto.LIMITE_CONTEXTO_CARACTERES = limite_original

    import jarvis.cerebro.voz_local.contexto as modulo

    original_busca = modulo._memorias_relevantes

    modulo._memorias_relevantes = lambda t: (_ for _ in ()).throw(
        RuntimeError("vault ilegível")
    )

    try:
        try:
            modulo.montar_contexto_sistema("qualquer coisa")
            quebrou = False

        except Exception:
            quebrou = True

        checar(
            quebrou,
            "(diagnóstico) a exceção sobe se _memorias_relevantes quebrar",
        )

    finally:
        modulo._memorias_relevantes = original_busca

    from jarvis.pacotes.memoria_obsidian import busca as busca_memoria

    original_buscar = busca_memoria.buscar_memorias
    busca_memoria.buscar_memorias = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("disco fora do ar")
    )

    try:
        texto_com_falha = contexto.montar_contexto_sistema("qual é o meu nome?")

        checar(
            bool(texto_com_falha) and "Fatos que você já sabe" not in texto_com_falha,
            "vault quebrado degrada para contexto sem fatos, sem estourar",
        )

    finally:
        busca_memoria.buscar_memorias = original_buscar

    enviados = {}

    class ClienteFalso:
        def publicar_texto(self, dados):
            enviados.update(dados)

            return (True, "enviado")

    async def principal():
        worker.ativo = True
        worker.loop = asyncio.get_running_loop()
        worker.cliente_mqtt = ClienteFalso()
        worker.transcricao_conversa = [
            {"role": "user", "content": "meu nome é Massaki"},
            {"role": "assistant", "content": "Anotado."},
            {"role": "user", "content": "qual é o meu nome?"},
        ]

        limite = config_local.TIMEOUT_RESPOSTA_SEGUNDOS
        config_local.TIMEOUT_RESPOSTA_SEGUNDOS = 1

        try:
            return await worker._pedir_resposta(
                {"texto": "qual é o meu nome?", "tom": "neutro", "sexo": "M"}
            )

        finally:
            config_local.TIMEOUT_RESPOSTA_SEGUNDOS = limite
            worker.loop = None
            worker.cliente_mqtt = None

    asyncio.run(principal())

    checar(
        enviados.get("texto") == "qual é o meu nome?"
        and enviados.get("tom") == "neutro"
        and enviados.get("sexo") == "M",
        "os três campos que já existiam continuam iguais",
    )

    checar(
        "historico" in enviados and "contexto_sistema" in enviados,
        f"e os dois campos novos vão junto ({sorted(enviados)})",
    )

    conteudos = [m["content"] for m in enviados["historico"]]

    checar(
        "meu nome é Massaki" in conteudos,
        "o histórico carrega o que foi dito nos turnos anteriores "
        "(o caso relatado: dizer o nome e perguntar depois)",
    )

    checar(
        conteudos.count("qual é o meu nome?") == 0,
        "e NÃO duplica a fala atual, que já vai no campo 'texto'",
    )

    checar(
        len(worker.transcricao_conversa) == 3,
        "montar o payload não mexe na transcrição do worker",
    )

    worker.transcricao_conversa = []


def testar_texto_da_resposta(worker):
    titulo("6i. O texto da resposta volta e entra no histórico")

    import threading

    import jarvis.cerebro.voz_local.cliente_local as modulo
    from jarvis.roteamento_hierarquico.roteador import ResultadoTurno

    class PropriedadesFalsas:
        def __init__(self, pares):
            self.UserProperty = pares

    class MensagemFalsa:
        def __init__(self, propriedades):
            self.topic = config_local.TOPICO_SAIDA
            self.payload = b"RIFF...."
            self.properties = propriedades

    extrair = ClienteVozLocal._texto_da_propriedade
    nome = config_local.PROPRIEDADE_TEXTO_RESPOSTA

    checar(
        extrair(MensagemFalsa(PropriedadesFalsas([(nome, "bom dia")])))
        == "bom dia",
        "lê o texto da user property",
    )

    checar(
        extrair(
            MensagemFalsa(
                PropriedadesFalsas(
                    [("outra", "lixo"), (nome, "com acentuação é assim")]
                )
            )
        )
        == "com acentuação é assim",
        "acha a property certa no meio de outras, com acento intacto",
    )

    checar(
        extrair(MensagemFalsa(PropriedadesFalsas([(nome, "   ")]))) is None
        and extrair(MensagemFalsa(PropriedadesFalsas([("texto2", "x")])))
        is None
        and extrair(MensagemFalsa(PropriedadesFalsas([]))) is None,
        "texto em branco, nome errado e lista vazia dão None",
    )

    class SemPropriedades:
        topic = config_local.TOPICO_SAIDA
        payload = b"RIFF...."

    checar(
        extrair(SemPropriedades()) is None
        and extrair(MensagemFalsa(None)) is None,
        "mensagem sem properties devolve None (servidor antigo ou v3.1.1)",
    )

    class PropriedadesQuebradas:
        @property
        def UserProperty(self):
            raise RuntimeError("property corrompida")

    checar(
        extrair(MensagemFalsa(PropriedadesQuebradas())) is None,
        "e uma property corrompida NÃO levanta (mataria a thread do paho)",
    )

    recebidos = []
    cliente = ClienteVozLocal(
        ao_receber_texto=lambda d: None,
        ao_receber_saida=lambda d, t=None: recebidos.append((d, t)),
        ao_receber_erro=lambda t: None,
    )
    cliente._ao_receber_mensagem(
        None,
        None,
        MensagemFalsa(PropriedadesFalsas([(nome, "olá")])),
    )

    checar(
        recebidos == [(b"RIFF....", "olá")],
        f"o handler entrega áudio E texto ao worker ({recebidos})",
    )

    worker.transcricao_conversa = []
    worker._registrar_fala_do_assistente("Seu nome é Massaki.")

    checar(
        worker.transcricao_conversa
        == [{"role": "assistant", "content": "Seu nome é Massaki."}],
        "a fala do assistente entra no histórico como 'assistant'",
    )

    worker.transcricao_conversa = []
    worker._registrar_fala_do_assistente(None)
    worker._registrar_fala_do_assistente("   ")

    checar(
        worker.transcricao_conversa == [],
        "texto ausente (servidor antigo) não vira entrada em branco",
    )

    falas = [
        "qual é o meu nome?",
        "meu nome é Massaki",
        "qual é o meu nome mesmo?",
    ]
    respostas = [
        "Não sei ainda, como você se chama?",
        "Prazer, Massaki.",
        "Seu nome é Massaki.",
    ]
    turno = {"i": 0}
    payloads = []

    async def capturar_falso(fila):
        if turno["i"] >= len(falas):
            worker.ativo = False

            return None

        return b"\x00\x01" * 16000

    async def transcrever_falso(pcm):
        return (
            "texto",
            {"texto": falas[turno["i"]], "tom": "neutro", "sexo": "M"},
        )

    async def rotear_falso(texto):
        return ResultadoTurno(resposta="", usou_ferramenta=False)

    async def reproduzir_falso(*args, **kwargs):
        return None

    class ServidorFalso:
        def publicar_texto(self, dados):
            payloads.append(json.loads(json.dumps(dados)))
            resposta = respostas[turno["i"]]
            turno["i"] += 1

            def entregar():
                time.sleep(0.02)
                worker._entregar_resposta(
                    ("audio", modulo.RespostaFalada(b"", resposta))
                )

            threading.Thread(target=entregar, daemon=True).start()

            return (True, "enviado")

    async def sem_contexto(*args, **kwargs):
        return ""

    originais = (
        worker._capturar_frase,
        worker._transcrever,
        worker._rotear,
        worker._reproduzir_resposta,
        worker.cliente_mqtt,
        modulo.contexto.montar_contexto_sistema,
    )
    worker._capturar_frase = capturar_falso
    worker._transcrever = transcrever_falso
    worker._rotear = rotear_falso
    worker._reproduzir_resposta = reproduzir_falso
    worker.cliente_mqtt = ServidorFalso()
    modulo.contexto.montar_contexto_sistema = lambda texto: ""
    worker.transcricao_conversa = []
    worker.ativo = True

    async def principal():
        worker.loop = asyncio.get_running_loop()

        await worker.ciclo_de_conversa(asyncio.Queue(), None)

    try:
        asyncio.run(principal())

    finally:
        (
            worker._capturar_frase,
            worker._transcrever,
            worker._rotear,
            worker._reproduzir_resposta,
            worker.cliente_mqtt,
            modulo.contexto.montar_contexto_sistema,
        ) = originais
        worker.ativo = False

    checar(
        len(payloads) == 3,
        f"os três turnos chegaram na etapa 2 ({len(payloads)})",
    )

    if len(payloads) == 3:
        historico = payloads[2].get("historico") or []
        papeis = [m["role"] for m in historico]
        conteudos = [m["content"] for m in historico]

        checar(
            "assistant" in papeis and "user" in papeis,
            f"o histórico do 3º turno tem OS DOIS lados ({papeis})",
        )

        checar(
            "Prazer, Massaki." in conteudos,
            "e carrega o que o ASSISTENTE respondeu no turno anterior",
        )

        checar(
            "meu nome é Massaki" in conteudos,
            "junto do que o usuário disse",
        )

        checar(
            falas[2] not in conteudos,
            "sem duplicar a fala atual, que já vai no campo 'texto'",
        )

        checar(
            papeis == ["user", "assistant", "user", "assistant"],
            f"na ordem real do diálogo ({papeis})",
        )

    worker.transcricao_conversa = []


def testar_tool_call_indevida():
    titulo("6j. O 400 de chamada de ferramenta indevida")

    from types import SimpleNamespace

    from langchain_core.messages import AIMessage

    from jarvis.roteamento_hierarquico import config as config_rot
    from jarvis.roteamento_hierarquico import roteador
    from jarvis.servicos import agentes
    from jarvis.servicos.agentes import agente as motor

    detectar = agentes.erros.e_chamada_de_ferramenta_indevida

    checar(
        detectar("Tool choice is none, but model called a tool"),
        "reconhece a mensagem da Groq",
    )
    checar(
        detectar("TOOL CHOICE IS NONE, BUT MODEL CALLED A TOOL"),
        "sem depender de caixa",
    )
    checar(
        not detectar("invalid_api_key")
        and not detectar("Rate limit reached ... tokens per minute")
        and not detectar(None)
        and not detectar(""),
        "e não confunde com 401, 429, None ou vazio",
    )

    class ErroFalso(Exception):
        def __init__(self, status, mensagem, headers=None):
            super().__init__(mensagem)
            self.response = SimpleNamespace(
                status_code=status,
                headers=headers or {},
            )

    MSG_TOOL = "Tool choice is none, but model called a tool"

    SUCESSO = AIMessage(content="FERRAMENTAS: salvar_memoria")

    class ModeloFalso:
        def __init__(self, sequencia, registro):
            self.sequencia = sequencia
            self.registro = registro

        def bind_tools(self, *args, **kwargs):
            return self

        def bind(self, *args, **kwargs):
            return self

        def invoke(self, mensagens):
            self.registro["chamadas"] += 1

            indice = min(
                self.registro["chamadas"] - 1, len(self.sequencia) - 1
            )
            item = self.sequencia[indice]

            if isinstance(item, Exception):
                raise item

            return item

    def rodar(sequencia):
        registro = {"chamadas": 0, "dormidas": []}

        criar_original = motor.modelos.criar_modelo
        sleep_original = motor.time.sleep

        motor.modelos.criar_modelo = (
            lambda *a, **k: ModeloFalso(sequencia, registro)
        )
        motor.time.sleep = registro["dormidas"].append

        try:
            resposta = roteador._consultar(
                roteador._pedido_groq(
                    "instrução de sistema",
                    "salve isso na memória",
                    "modelo-de-teste",
                )
            )

        finally:
            motor.modelos.criar_modelo = criar_original
            motor.time.sleep = sleep_original

        return (
            resposta,
            registro["chamadas"],
            registro["dormidas"],
        )

    resposta, n, dormiu = rodar([ErroFalso(400, MSG_TOOL), SUCESSO])

    checar(resposta.sucesso and n == 2, f"repete e acerta na 2ª tentativa ({n} chamadas)")
    checar(
        resposta.texto == "FERRAMENTAS: salvar_memoria",
        "e entrega a resposta boa, não o erro",
    )
    checar(
        dormiu == [],
        f"sem espera entre as tentativas — não é rate limit ({dormiu})",
    )

    resposta, n, _ = rodar([ErroFalso(400, MSG_TOOL)])

    checar(
        not resposta.sucesso
        and n == config_rot.TENTATIVAS_TOOL_CALL_INDEVIDA,
        f"desiste após {config_rot.TENTATIVAS_TOOL_CALL_INDEVIDA} "
        f"tentativas ({n} chamadas)",
    )
    checar(
        "Tool choice is none" in resposta.erro,
        "e preserva o erro original da Groq na mensagem final",
    )
    checar(
        resposta.tipo_erro == agentes.erros.FERRAMENTA_INDEVIDA,
        "marcando o tipo, que é o que o plano B vai consultar",
    )

    resposta, n, _ = rodar([ErroFalso(401, "invalid_api_key")])
    checar(not resposta.sucesso and n == 1, f"401 não repete ({n} chamada)")

    resposta, n, _ = rodar([ErroFalso(400, "malformed body")])
    checar(not resposta.sucesso and n == 1, f"400 comum não repete ({n} chamada)")

    resposta, n, _ = rodar(
        [
            ErroFalso(400, MSG_TOOL),
            ErroFalso(429, "Rate limit reached"),
            SUCESSO,
        ]
    )
    checar(
        resposta.sucesso and n == 3,
        f"429 no meio não consome as tentativas do 400 ({n} chamadas)",
    )

    historico = [
        {"role": "user", "content": "Qual é o assunto que eu mais gosto?"},
        {"role": "assistant", "content": "Ainda não sei, me conta."},
    ]

    vistas = []

    def consulta_falsa(pedido):
        vistas.append(list(pedido.historico or []))

        if pedido.historico:
            return agentes.RespostaAgente(
                False,
                erro=f"Falha na chamada à Groq (400): {MSG_TOOL}",
                tipo_erro=agentes.erros.FERRAMENTA_INDEVIDA,
            )

        return agentes.RespostaAgente(
            True,
            texto="Claro, vou lembrar disso.",
            uso=agentes.UsoTokens(total=1200),
        )

    original = roteador._consultar
    roteador._consultar = consulta_falsa

    try:
        resultado = roteador.processar_turno(
            "Salve na sua memória que gosto de tecnologia.",
            list(historico),
        )

    finally:
        roteador._consultar = original

    checar(
        len(vistas) == 2,
        f"a etapa 1 é refeita uma segunda vez, e o turno acaba aí "
        f"({len(vistas)} chamadas)",
    )

    if len(vistas) == 2:
        checar(
            any(m["role"] == "assistant" for m in vistas[0]),
            "a primeira tentativa leva o histórico",
        )
        checar(
            vistas[1] == [],
            f"e a segunda vai SEM o histórico ({vistas[1]})",
        )

    checar(
        not resultado.falhou,
        "o turno se salva em vez de morrer no 400 (era o bug relatado)",
    )

    vistas.clear()
    roteador._consultar = lambda pedido: agentes.RespostaAgente(
        False,
        erro=f"Falha na chamada à Groq (400): {MSG_TOOL}",
        tipo_erro=agentes.erros.FERRAMENTA_INDEVIDA,
    )

    try:
        resultado = roteador.processar_turno("qualquer coisa", [])

    finally:
        roteador._consultar = original

    checar(
        resultado.falhou,
        "sem histórico para remover, a falha é reportada como falha",
    )


def testar_recusas(worker):
    titulo("7. Recusas explícitas (o que o protocolo local não permite)")

    erros = []
    worker.erro_recebido.connect(erros.append)

    try:
        worker.solicitar_analise_tela()
        worker.solicitar_analise_camera()

        checar(
            worker.enviar_texto_da_ui("oi") is False,
            "enviar_texto_da_ui devolve False (a janela de chat avisa)",
        )

        checar(
            worker.enviar_imagem_da_ui(b"x", "image/jpeg") is False,
            "enviar_imagem_da_ui devolve False",
        )

        checar(
            len(erros) == 4,
            f"as quatro recusas apareceram na interface ({len(erros)})",
        )

        checar(
            all("local" in erro for erro in erros),
            "cada recusa explica que é limitação do cérebro local",
        )

    finally:
        worker.erro_recebido.disconnect(erros.append)

    checar(
        isinstance(worker.transcricao_conversa, list),
        "transcricao_conversa existe (a janela a lê no fim da chamada)",
    )

    checar(
        isinstance(worker.slug_perfil, str) and worker.slug_perfil,
        f"slug_perfil resolvido ({worker.slug_perfil})",
    )


def testar_chat_sobreposto():
    titulo("9. Chat translúcido sobre a esfera")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from jarvis.nucleo.sinalizador import obter_sinalizador
    from jarvis.ui import painel_chat_sobreposto as painel_chat
    from jarvis.ui.janela_principal import MainWindow
    from jarvis.ui.visualizador_alfred import VisualizadorAlfred

    janela = MainWindow()
    janela.resize(1380, 760)
    janela.show()
    QApplication.instance().processEvents()

    chat = janela.chat_sobreposto
    esfera = janela.visualizador

    checar(
        isinstance(esfera, VisualizadorAlfred)
        and isinstance(esfera, QWidget)
        and not hasattr(esfera, "makeCurrent"),
        "a esfera é QWidget puro (sem OpenGL) — por isso o alfa compõe "
        "direto, sem WA_AlwaysStackOnTop",
    )

    checar(
        chat.parentWidget() is esfera,
        "o chat é FILHO da esfera (fora do layout, senão a empurraria)",
    )

    checar(
        not chat.texto.viewport().autoFillBackground()
        and chat.texto.viewport().testAttribute(
            Qt.WA_TranslucentBackground
        ),
        "o viewport do QTextEdit é transparente (a armadilha do "
        "QAbstractScrollArea)",
    )

    checar(
        chat.testAttribute(Qt.WA_NoSystemBackground),
        "e o painel não pinta fundo de sistema (deixa a esfera aparecer)",
    )

    checar(
        chat.testAttribute(Qt.WA_TransparentForMouseEvents),
        "o painel não rouba clique de quem está embaixo",
    )

    checar(
        0.0 <= painel_chat.OPACIDADE_FUNDO <= 1.0
        and 0.0 <= painel_chat.OPACIDADE_TEXTO <= 1.0,
        f"as opacidades são constantes nomeadas "
        f"(fundo {painel_chat.OPACIDADE_FUNDO}, "
        f"texto {painel_chat.OPACIDADE_TEXTO})",
    )

    cor = painel_chat._com_alfa(
        painel_chat.estilo.FUNDO_PAINEL,
        painel_chat.OPACIDADE_FUNDO,
    )

    checar(
        0 < cor.alpha() < 255,
        f"o fundo é de fato semitransparente (alfa {cor.alpha()}/255) — "
        "nem opaco, nem invisível",
    )

    chat.limpar()
    QApplication.instance().processEvents()

    checar(
        not chat.isVisible(),
        "sem resposta nenhuma o painel fica escondido (não suja a esfera)",
    )

    obter_sinalizador().resposta_texto_recebida.emit("Seu nome é Massaki.")
    QApplication.instance().processEvents()

    checar(
        chat.isVisible()
        and "Massaki" in chat.texto.toPlainText(),
        "a resposta chega pelo sinalizador e o painel aparece",
    )

    obter_sinalizador().resposta_texto_recebida.emit("   ")
    QApplication.instance().processEvents()

    checar(
        chat.texto.toPlainText().count("Massaki") == 1,
        "texto vazio ou só com espaço é ignorado",
    )

    def dentro():
        return (
            chat.x() >= 0
            and chat.y() >= 0
            and chat.x() + chat.width() <= esfera.width()
            and chat.y() + chat.height() <= esfera.height()
        )

    checar(dentro(), f"o painel cabe dentro da esfera {chat.geometry().getRect()}")

    largura_antes = chat.width()
    janela.resize(1600, 900)
    QApplication.instance().processEvents()

    checar(
        chat.width() != largura_antes and dentro(),
        f"e acompanha o redimensionamento da janela "
        f"({largura_antes} -> {chat.width()})",
    )

    for i in range(painel_chat.MAXIMO_RESPOSTAS + 10):
        chat.adicionar_resposta(f"resposta numero {i}")

    QApplication.instance().processEvents()

    guardadas = [
        linha
        for linha in chat.texto.toPlainText().split("\n\n")
        if linha.strip()
    ]

    checar(
        len(guardadas) == painel_chat.MAXIMO_RESPOSTAS,
        f"o histórico é limitado a {painel_chat.MAXIMO_RESPOSTAS} "
        f"respostas ({len(guardadas)})",
    )

    checar(
        "resposta numero 39" in chat.texto.toPlainText()
        and "resposta numero 0" not in chat.texto.toPlainText(),
        "e o que sobra são as MAIS RECENTES",
    )

    def medir(repeticoes=40):
        esfera.update()
        QApplication.instance().processEvents()
        inicio = time.perf_counter()

        for _ in range(repeticoes):
            esfera.update()
            QApplication.instance().processEvents()

        return (time.perf_counter() - inicio) / repeticoes

    chat.show()
    QApplication.instance().processEvents()
    com_painel = medir()

    chat.hide()
    QApplication.instance().processEvents()
    sem_painel = medir()

    orcamento = 1.0 / VisualizadorAlfred.FPS_FALANDO
    custo = com_painel - sem_painel

    checar(
        custo < orcamento / 10,
        f"o painel custa {custo * 1000:+.2f} ms por quadro, contra um "
        f"orçamento de {orcamento * 1000:.0f} ms a "
        f"{VisualizadorAlfred.FPS_FALANDO} FPS",
    )

    chat.limpar()
    QApplication.instance().processEvents()

    checar(
        not chat.isVisible() and chat.texto.toPlainText() == "",
        "limpar() esvazia e esconde (usado ao iniciar cada chamada)",
    )

    janela.close()


def testar_local_alimenta_chat(worker):
    titulo("10. O cérebro local também entrega o texto ao chat")

    from jarvis.nucleo.sinalizador import obter_sinalizador

    recebidos = []
    obter_sinalizador().resposta_texto_recebida.connect(recebidos.append)

    try:
        worker.transcricao_conversa = []
        worker._registrar_fala_do_assistente("Seu nome é Massaki.")
        QApplication.instance().processEvents()

        checar(
            recebidos == ["Seu nome é Massaki."],
            f"_registrar_fala_do_assistente emite para o chat ({recebidos})",
        )

        checar(
            worker.transcricao_conversa
            == [{"role": "assistant", "content": "Seu nome é Massaki."}],
            "e continua alimentando o histórico da conversa, como antes",
        )

        recebidos.clear()
        worker._registrar_fala_do_assistente(None)
        worker._registrar_fala_do_assistente("   ")
        QApplication.instance().processEvents()

        checar(
            recebidos == [],
            "texto ausente (servidor antigo) não emite nada",
        )

    finally:
        obter_sinalizador().resposta_texto_recebida.disconnect(
            recebidos.append
        )
        worker.transcricao_conversa = []


def testar_gemini_intacto():
    titulo("8. O caminho do Gemini não foi tocado")

    fonte = Path("jarvis/cerebro/gemini/cliente_live.py").read_text(encoding="utf-8")

    checar(
        "voz_local" not in fonte,
        "cliente_live.py não tem nenhuma referência ao cérebro local",
    )

    checar(
        fonte.count("send_realtime_input(") >= 1
        and "sessao.send_realtime_input(" in fonte,
        "o envio do microfone para o Gemini segue no lugar",
    )

    checar(
        fonte.count("self.alfred_falando\n                and not self.interrupcao_habilitada")
        + fonte.count("self.alfred_falando\n                    and not self.interrupcao_habilitada")
        + fonte.count("self.alfred_falando\n                        and not self.interrupcao_habilitada")
        == 3,
        "as 3 guardas de microfone do Gemini seguem com a exceção de interrupção",
    )

    janela = Path("jarvis/ui/janela_principal.py").read_text(encoding="utf-8")

    checar(
        janela.count("_classe_do_worker()") >= 1
        and "from jarvis.cerebro.voz_local import VozLocalWorker" in janela,
        "a troca de cérebro segue concentrada em _classe_do_worker",
    )

    checar(
        "VozLocal" not in janela.replace(
            "        from jarvis.cerebro.voz_local import VozLocalWorker\n\n"
            "        return VozLocalWorker\n",
            "",
        ),
        "nenhuma UI nova foi adicionada à janela principal",
    )


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    worker = VozLocalWorker()

    worker.ativo = False

    testar_paridade()
    testar_provedor()
    testar_selects_de_cerebro()
    testar_wav()
    testar_vad(worker)
    testar_vad_silero(worker)
    testar_barge_in(worker)
    testar_mqtt_real(worker)
    testar_fluxo_worker(worker)
    testar_roteamento(worker)
    testar_falha_de_roteamento(worker)
    testar_retry_groq()
    testar_captura_para_ferramentas_visuais(worker)
    testar_visao_portada()
    testar_segunda_opiniao_provedor()
    testar_memoria_local(worker)
    testar_texto_da_resposta(worker)
    testar_tool_call_indevida()
    testar_recusas(worker)
    testar_gemini_intacto()
    testar_chat_sobreposto()
    testar_local_alimenta_chat(worker)

    print(f"\n{aprovados} aprovados, {reprovados} reprovados")

    return 1 if reprovados else 0


if __name__ == "__main__":
    sys.exit(main())
