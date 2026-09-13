import os
import shutil
import urllib.request

import numpy as np

from jarvis.caminhos import PASTA_DADOS, garantir_pasta

from . import config


JANELA_AMOSTRAS = 512

CONTEXTO_AMOSTRAS = 64

FORMA_ESTADO = (2, 1, 128)

NOME_MODELO = "silero_vad_16k_op15.onnx"

PASTA_MODELOS = PASTA_DADOS / "modelos"
CAMINHO_MODELO = PASTA_MODELOS / NOME_MODELO

URL_MODELO = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/"
    "v6.2.1/src/silero_vad/data/" + NOME_MODELO
)

TIMEOUT_DOWNLOAD_SEGUNDOS = 30


class VadIndisponivel(Exception):
    pass


def _caminho_do_pacote_instalado():
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
        self._estado = np.zeros(FORMA_ESTADO, dtype=np.float32)
        self._contexto = np.zeros(CONTEXTO_AMOSTRAS, dtype=np.float32)
        self._resto = np.zeros(0, dtype=np.float32)

    def probabilidade(self, bloco_bytes):
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
        # Classifica por CONTEÚDO (Silero), nunca por volume.
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

        self._contexto = janela[-CONTEXTO_AMOSTRAS:]

        return float(saida[0][0])
