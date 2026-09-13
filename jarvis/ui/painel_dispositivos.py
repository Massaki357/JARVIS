import sounddevice as sd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QWidget,
)

from jarvis.nucleo import preferencias

PADRAO_DO_SISTEMA = "Padrão do Windows"

HOSTAPIS_OCULTAS = {"Windows WDM-KS"}

NOMES_OCULTOS = (
    "mapeador de som",
    "driver de captura de som",
    "driver de som primário",
    "driver de som primario",
    "sound mapper",
    "primary sound",
)


def _deve_ocultar(nome, nome_hostapi):
    if nome_hostapi in HOSTAPIS_OCULTAS:
        return True

    minusculo = nome.lower()

    return any(trecho in minusculo for trecho in NOMES_OCULTOS)


def _hostapi_preferida(entrada):
    try:
        padrao = sd.default.device
        indice = padrao[0] if entrada else padrao[1]

        if indice is not None and indice >= 0:
            return sd.query_devices(indice)["hostapi"]

    except Exception:
        pass

    return None


def _mesmo_aparelho(nome_a, nome_b):
    menor, maior = sorted((nome_a, nome_b), key=len)

    return maior.startswith(menor)


def listar_dispositivos(entrada):
    try:
        dispositivos = list(enumerate(sd.query_devices()))

    except Exception as erro:
        print(f"[DISPOSITIVOS] Não consegui listar o áudio: {erro}")
        return []

    campo = "max_input_channels" if entrada else "max_output_channels"
    preferida = _hostapi_preferida(entrada)

    try:
        nomes_hostapi = [api["name"] for api in sd.query_hostapis()]

    except Exception:
        nomes_hostapi = []

    grupos = []
    ocultados = 0

    for indice, dispositivo in dispositivos:
        if dispositivo.get(campo, 0) < 1:
            continue

        nome = " ".join(
            str(dispositivo.get("name") or "").split()
        ).strip()

        if not nome:
            continue

        indice_api = dispositivo.get("hostapi")

        nome_api = (
            nomes_hostapi[indice_api]
            if isinstance(indice_api, int)
            and 0 <= indice_api < len(nomes_hostapi)
            else ""
        )

        if _deve_ocultar(nome, nome_api):
            ocultados += 1
            continue

        for grupo in grupos:
            if _mesmo_aparelho(grupo["nome"], nome):
                if len(nome) > len(grupo["nome"]):
                    grupo["nome"] = nome

                grupo["variantes"].append((indice, dispositivo))
                break

        else:
            grupos.append(
                {
                    "nome": nome,
                    "variantes": [(indice, dispositivo)],
                }
            )

    if not grupos and ocultados:
        return [
            (
                " ".join(str(d.get("name") or "").split()),
                i,
            )
            for i, d in dispositivos
            if d.get(campo, 0) >= 1 and (d.get("name") or "").strip()
        ]

    resultado = []

    for grupo in grupos:
        escolhido = None

        for indice, dispositivo in grupo["variantes"]:
            if dispositivo.get("hostapi") == preferida:
                escolhido = indice
                break

        if escolhido is None:
            escolhido = grupo["variantes"][0][0]

        resultado.append((grupo["nome"], escolhido))

    return resultado


def _resolver_indice(nome_guardado, entrada):
    if not nome_guardado:
        return None

    for nome, indice in listar_dispositivos(entrada):
        if _mesmo_aparelho(nome, nome_guardado):
            return indice

    return None


def aplicar_preferencias():
    entrada_salva = preferencias.dispositivo_entrada()
    saida_salva = preferencias.dispositivo_saida()

    indice_entrada = _resolver_indice(entrada_salva, True)
    indice_saida = _resolver_indice(saida_salva, False)

    if entrada_salva and indice_entrada is None:
        print(
            f"[DISPOSITIVOS] O microfone '{entrada_salva}' não está "
            "disponível agora — usando o padrão do Windows."
        )

    if saida_salva and indice_saida is None:
        print(
            f"[DISPOSITIVOS] O alto-falante '{saida_salva}' não está "
            "disponível agora — usando o padrão do Windows."
        )

    try:
        atual = list(sd.default.device)

        sd.default.device = [
            indice_entrada if indice_entrada is not None else atual[0],
            indice_saida if indice_saida is not None else atual[1],
        ]

        return True

    except Exception as erro:
        print(
            f"[DISPOSITIVOS] Não consegui aplicar a seleção: {erro}"
        )

        return False


class PainelDispositivos(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._montando = True

        self._montar()
        self.recarregar()

        self._montando = False

    def _montar(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(4)

        rotulo_micro = QLabel("Microfone")
        rotulo_micro.setObjectName("statusTitulo")

        rotulo_saida = QLabel("Alto-falante")
        rotulo_saida.setObjectName("statusTitulo")

        self.combo_microfone = QComboBox()
        self.combo_microfone.setObjectName("comboDispositivo")
        self.combo_microfone.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.combo_alto_falante = QComboBox()
        self.combo_alto_falante.setObjectName("comboDispositivo")
        self.combo_alto_falante.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        estilo_combo = (
            "QComboBox#comboDispositivo {"
            "    min-height: 0px;"
            "    padding: 4px 8px;"
            "    font-size: 10px;"
            "}"
        )

        self.combo_microfone.setStyleSheet(estilo_combo)
        self.combo_alto_falante.setStyleSheet(estilo_combo)

        layout.addWidget(rotulo_micro, 0, 0)
        layout.addWidget(rotulo_saida, 0, 1)
        layout.addWidget(self.combo_microfone, 1, 0)
        layout.addWidget(self.combo_alto_falante, 1, 1)

        self.combo_microfone.currentIndexChanged.connect(
            lambda _: self._ao_trocar(True)
        )

        self.combo_alto_falante.currentIndexChanged.connect(
            lambda _: self._ao_trocar(False)
        )

    def _preencher(self, combo, entrada, nome_salvo):
        combo.clear()
        combo.addItem(PADRAO_DO_SISTEMA, None)

        for nome, _indice in listar_dispositivos(entrada):
            combo.addItem(nome, nome)

        alvo = 0

        if nome_salvo:
            for posicao in range(1, combo.count()):
                if _mesmo_aparelho(
                    combo.itemData(posicao) or "",
                    nome_salvo,
                ):
                    alvo = posicao
                    break

        combo.setCurrentIndex(alvo)

    def recarregar(self):
        estava_montando = self._montando
        self._montando = True

        try:
            self._preencher(
                self.combo_microfone,
                True,
                preferencias.dispositivo_entrada(),
            )

            self._preencher(
                self.combo_alto_falante,
                False,
                preferencias.dispositivo_saida(),
            )

        finally:
            self._montando = estava_montando

        aplicar_preferencias()

    def _ao_trocar(self, entrada):
        if self._montando:
            return

        combo = (
            self.combo_microfone if entrada
            else self.combo_alto_falante
        )

        nome = combo.currentData()

        preferencias.salvar_preferencia(
            "microfone" if entrada else "alto_falante",
            nome or "",
        )

        aplicar_preferencias()

        if entrada:
            try:
                from jarvis.pacotes import ativacao_voz

                if ativacao_voz.esta_ativo():
                    ativacao_voz.pausar()
                    ativacao_voz.retomar()

            except Exception as erro:
                print(
                    "[DISPOSITIVOS] Não consegui reiniciar a "
                    f"ativação por voz: {erro}"
                )

        print(
            "[DISPOSITIVOS] "
            + ("Microfone" if entrada else "Alto-falante")
            + f": {nome or PADRAO_DO_SISTEMA}"
        )
