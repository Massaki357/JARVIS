# Detecção de fala do modo local — Silero VAD rodando por onnxruntime.
#
# POR QUE ISTO EXISTE, e o que ele substituiu:
#
# O modo local é o único dos três cérebros que precisa decidir sozinho
# onde a frase termina (o Gemini Live e a Realtime API têm VAD do lado
# do servidor; o alfred-server recebe arquivo pronto). Essa decisão era
# tomada por AMPLITUDE: calcular_nivel_audio devolvia o pico
# normalizado do bloco e ele era comparado com um limiar fixo.
#
# O problema disso não é de ajuste de limiar, é de natureza da medida.
# Amplitude não distingue fala de nada — só mede o quanto o sinal é
# alto. Com ruído de fundo contínuo e alto (moto passando, ventilador,
# música tocando), TODO bloco fica acima do limiar, o contador de
# silêncio nunca sobe, e a frase nunca fecha: o microfone segue
# gravando enquanto o barulho durar. Medido nesta máquina, com o limiar
# padrão de 0.12: ruído branco forte e zumbido de motor a 90 Hz foram
# classificados como fala em 100% dos blocos.
#
# O Silero decide por CONTEÚDO: é um modelo pequeno, treinado para
# separar voz humana de qualquer outro som, e devolve a probabilidade
# de o trecho conter fala. Nos mesmos sinais acima ele deu 0.0% e
# 14.5% de blocos acima de 0.5, contra 72.1% numa fala de verdade —
# ou seja, o ruído deixa de segurar a frase aberta.
#
# ONNXRUNTIME EM VEZ DO PACOTE silero-vad, e isto é deliberado: o
# pacote do PyPI declara torch e torchaudio como dependências
# obrigatórias, e o __init__.py dele importa torch mesmo no caminho
# ONNX (confirmado: "import torch" no topo de utils_vad.py, que
# model.py importa). Seriam ~250 MB de dependência num projeto que não
# tem nenhum outro uso de torch, para rodar um modelo de 1,2 MB. O
# onnxruntime sozinho pesa ~15 MB e executa o mesmo modelo.
#
# O CONTRATO DO MODELO foi lido do wrapper oficial
# (silero_vad/utils_vad.py::OnnxWrapper.__call__), não adivinhado, e
# tem duas sutilezas que fazem toda a diferença:
#
#   1. A janela é de EXATAMENTE 512 amostras a 16 kHz. Nem 1024, nem
#      "o tamanho do bloco".
#   2. Cada chamada recebe 576 amostras: as 64 ÚLTIMAS amostras da
#      janela anterior (o "contexto") na frente das 512 atuais. Sem
#      esse contexto o modelo devolve ~0.001 para tudo, fala inclusive
#      — foi exatamente o que aconteceu na primeira tentativa aqui, e
#      o sintoma (probabilidade baixa para todo mundo) parece um
#      modelo quebrado, não uma entrada malformada.
#
# Além disso o modelo é RECORRENTE: carrega um estado (2, 1, 128) de
# uma janela para a outra. Por isso existe zerar() — entre uma frase e
# outra o estado é reiniciado, senão a cauda de uma influencia o
# começo da seguinte.
import os
import shutil
import urllib.request

import numpy as np

from jarvis.caminhos import PASTA_DADOS, garantir_pasta

from . import config


# Amostras por janela de inferência, a 16 kHz. Valor do modelo, não
# escolha nossa — ver o contrato acima.
JANELA_AMOSTRAS = 512

# Amostras da janela anterior que entram na frente da atual.
CONTEXTO_AMOSTRAS = 64

# Formato do estado recorrente do modelo.
FORMA_ESTADO = (2, 1, 128)

# Nome do arquivo do modelo. É a variante "16k_op15": só 16 kHz (que é
# exatamente a taxa que este worker captura) e a menor das quatro que
# o projeto Silero publica — 1,2 MB contra 2,2 MB da genérica.
NOME_MODELO = "silero_vad_16k_op15.onnx"

# Onde o modelo fica nesta máquina. Em dados/, e não ao lado do
# código, pela mesma regra que vale para o resto do projeto: jarvis/ é
# fonte, dados/ é o que esta máquina baixou ou gerou.
PASTA_MODELOS = PASTA_DADOS / "modelos"
CAMINHO_MODELO = PASTA_MODELOS / NOME_MODELO

# De onde baixar quando ainda não existir localmente. Fixado numa tag,
# nunca em "master": o arquivo tem que ser o mesmo em qualquer máquina
# e em qualquer dia, e um modelo trocado embaixo do projeto mudaria o
# comportamento do VAD sem nenhuma alteração de código.
URL_MODELO = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/"
    "v6.2.1/src/silero_vad/data/" + NOME_MODELO
)

TIMEOUT_DOWNLOAD_SEGUNDOS = 30


class VadIndisponivel(Exception):
    """
    O modelo ou o onnxruntime não estão utilizáveis nesta máquina.

    Existe como exceção própria para o worker poder distinguir "o VAD
    não subiu" (cai para o modo por amplitude, avisando) de qualquer
    outro erro.
    """


def _caminho_do_pacote_instalado():
    """
    O modelo que vem dentro do pacote silero-vad, quando ele estiver
    instalado. Serve como fonte LOCAL: se alguém instalou o pacote
    (com ou sem torch), não faz sentido baixar de novo o mesmo
    arquivo. Nada aqui importa silero_vad — só procura o arquivo, o
    que evita o "import torch" do __init__ dele.
    """
    try:
        import importlib.util

        spec = importlib.util.find_spec("silero_vad")

        if spec is None or not spec.submodule_search_locations:
            return None

        for raiz in spec.submodule_search_locations:
            candidato = os.path.join(raiz, "data", NOME_MODELO)

            if os.path.isfile(candidato):
                return candidato

    except Exception:
        pass

    return None


def obter_modelo():
    """
    Caminho do arquivo .onnx, baixando-o na primeira vez se preciso.

    A ordem é do mais barato para o mais caro: variável de ambiente,
    cache local, cópia que veio no pacote silero-vad, download. Mesma
    ideia do modelo do Vosk em jarvis/pacotes/ativacao_voz/, que
    também se resolve sozinho na primeira execução e fica em cache.
    """
    override = os.getenv("VOZ_LOCAL_MODELO_VAD", "").strip()

    if override:
        if not os.path.isfile(override):
            raise VadIndisponivel(
                f"VOZ_LOCAL_MODELO_VAD aponta para um arquivo que não "
                f"existe: {override}"
            )

        return override

    if CAMINHO_MODELO.is_file():
        return str(CAMINHO_MODELO)

    garantir_pasta(PASTA_MODELOS)

    do_pacote = _caminho_do_pacote_instalado()

    if do_pacote:
        shutil.copyfile(do_pacote, CAMINHO_MODELO)
        print(
            f"[VOZ LOCAL] Modelo do VAD copiado do pacote silero-vad "
            f"para {CAMINHO_MODELO}."
        )

        return str(CAMINHO_MODELO)

    print(
        f"[VOZ LOCAL] Baixando o modelo do VAD (~1,2 MB) de {URL_MODELO}..."
    )

    try:
        # Escreve num temporário e só então renomeia: um download
        # interrompido no meio deixaria um .onnx truncado no cache, e
        # a execução seguinte o encontraria e tentaria carregá-lo.
        temporario = CAMINHO_MODELO.with_suffix(".onnx.parcial")

        with urllib.request.urlopen(
            URL_MODELO, timeout=TIMEOUT_DOWNLOAD_SEGUNDOS
        ) as resposta, open(temporario, "wb") as destino:
            shutil.copyfileobj(resposta, destino)

        temporario.replace(CAMINHO_MODELO)

    except Exception as erro:
        raise VadIndisponivel(
            f"não consegui obter o modelo do VAD ({erro})"
        ) from erro

    print(f"[VOZ LOCAL] Modelo do VAD salvo em {CAMINHO_MODELO}.")

    return str(CAMINHO_MODELO)


class DetectorDeFala:
    """
    Classifica blocos de PCM 16 bits mono 16 kHz em fala / não-fala.

    Uso, um bloco por vez, na ordem em que chegam do microfone:

        detector = DetectorDeFala()
        if detector.tem_fala(bloco_bytes):
            ...

    e zerar() entre uma frase e outra.

    Aceita bloco de QUALQUER tamanho: o que sobra de uma chamada fica
    guardado e entra na frente da próxima. O worker manda blocos de
    1024 amostras, que são exatamente duas janelas, mas depender disso
    quebraria o dia em que BLOCO mudasse.
    """

    def __init__(self, caminho_modelo=None):
        try:
            import onnxruntime as ort

        except ImportError as erro:
            raise VadIndisponivel(
                "onnxruntime não está instalado (pip install onnxruntime)"
            ) from erro

        caminho = caminho_modelo or obter_modelo()

        try:
            opcoes = ort.SessionOptions()

            # Uma thread para cada coisa. O modelo é minúsculo e roda
            # em fração de milissegundo; deixar o onnxruntime abrir um
            # pool de threads por janela custaria mais em coordenação
            # do que a conta em si, e ainda disputaria CPU com a
            # captura de áudio. É também o que o wrapper oficial faz.
            opcoes.inter_op_num_threads = 1
            opcoes.intra_op_num_threads = 1

            self._sessao = ort.InferenceSession(
                caminho,
                opcoes,
                providers=["CPUExecutionProvider"],
            )

        except Exception as erro:
            raise VadIndisponivel(
                f"não consegui carregar o modelo do VAD ({erro})"
            ) from erro

        self._taxa = np.array(config.TAXA_VAD, dtype=np.int64)
        self.caminho_modelo = caminho

        self.zerar()

    def zerar(self):
        """
        Reinicia o estado recorrente, o contexto e o resto de amostras.

        Chamado entre frases: o modelo carrega estado de uma janela
        para a outra, e a cauda de uma frase não deve influenciar a
        classificação do começo da seguinte.
        """
        self._estado = np.zeros(FORMA_ESTADO, dtype=np.float32)
        self._contexto = np.zeros(CONTEXTO_AMOSTRAS, dtype=np.float32)
        self._resto = np.zeros(0, dtype=np.float32)

    def probabilidade(self, bloco_bytes):
        """
        Maior probabilidade de fala entre as janelas deste bloco.

        MAIOR, e não média: um bloco de 64 ms pode conter o começo de
        uma palavra na segunda metade e nada na primeira. Tirar a
        média nesse caso esconderia o início da fala, que é justamente
        o instante mais importante para não cortar a primeira sílaba.

        Devolve 0.0 quando o bloco ainda não completou uma janela
        inteira — o áudio não é descartado, fica guardado para a
        próxima chamada.
        """
        if not bloco_bytes:
            return 0.0

        amostras = (
            np.frombuffer(bloco_bytes, dtype=np.int16).astype(np.float32)
            / 32768.0
        )

        if self._resto.size:
            amostras = np.concatenate([self._resto, amostras])

        total_janelas = amostras.size // JANELA_AMOSTRAS

        if total_janelas == 0:
            self._resto = amostras

            return 0.0

        usadas = total_janelas * JANELA_AMOSTRAS
        self._resto = amostras[usadas:]

        maior = 0.0

        for i in range(total_janelas):
            janela = amostras[i * JANELA_AMOSTRAS:(i + 1) * JANELA_AMOSTRAS]
            maior = max(maior, self._inferir(janela))

        return maior

    def tem_fala(self, bloco_bytes):
        """
        True se este bloco contém fala humana.

        É o substituto direto do antigo "nivel >= config.LIMIAR_VOZ".
        """
        return self.probabilidade(bloco_bytes) >= config.LIMIAR_PROB_FALA

    def _inferir(self, janela):
        entrada = np.concatenate([self._contexto, janela]).reshape(1, -1)

        saida, self._estado = self._sessao.run(
            None,
            {
                "input": entrada,
                "state": self._estado,
                "sr": self._taxa,
            },
        )

        # O contexto da próxima janela são as últimas amostras DESTA,
        # sem o contexto que veio na frente dela.
        self._contexto = janela[-CONTEXTO_AMOSTRAS:]

        return float(saida[0][0])
