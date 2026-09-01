# Seleção de microfone e alto-falante na tela inicial.
#
# O Windows expõe o MESMO aparelho várias vezes, uma por host API
# (MME, DirectSound, WASAPI, WDM-KS). Nesta máquina, por exemplo, são
# 46 entradas para meia dúzia de aparelhos reais — jogar essa lista
# crua num select seria inútil. Por isso as duplicatas são agrupadas e
# aparece um item por aparelho.
#
# Duas decisões que valem ser explícitas:
#
#   1. O nome exibido vem da variante mais completa. O MME corta os
#      nomes em 31 caracteres ("Microfone (HyperX Cloud Flight"),
#      enquanto o DirectSound traz o nome inteiro ("Microfone (HyperX
#      Cloud Flight for PS)"). O agrupamento junta as duas por prefixo.
#
#   2. O índice usado é o da host API que o próprio PortAudio já
#      considera padrão nesta máquina. O app sempre usou essa API sem
#      dizer, e o áudio aqui é justamente a parte frágil do projeto —
#      não é hora de trocar a API por baixo junto com a novidade.
#
# O que é guardado no config.json é o NOME do aparelho, nunca o
# índice: índice muda quando qualquer dispositivo é conectado ou
# removido, e o usuário acabaria com o microfone errado selecionado
# sem ter mexido em nada.
import sounddevice as sd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QWidget,
)

from jarvis.nucleo import preferencias

# Texto da opção que devolve a escolha para o Windows.
PADRAO_DO_SISTEMA = "Padrão do Windows"

# Host APIs escondidas do select. WDM-KS é a camada bruta do kernel:
# ela repete todos os aparelhos que as outras APIs já mostram, com
# nomes ruins ("Input ()", "Output 1 (...)") e, num caso real desta
# máquina, um caminho de driver com quebra de linha no meio do nome.
# Nada que o usuário queira escolher numa lista.
HOSTAPIS_OCULTAS = {"Windows WDM-KS"}

# Pseudo-dispositivos que significam "o que o Windows estiver usando".
# Ficam de fora porque a opção "Padrão do Windows" já faz exatamente
# isso, e de forma mais clara.
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
    """
    Host API que o PortAudio já usa por padrão nesta máquina, para a
    direção pedida. Manter a mesma preserva exatamente o
    comportamento de áudio que o app sempre teve.
    """
    try:
        padrao = sd.default.device
        indice = padrao[0] if entrada else padrao[1]

        if indice is not None and indice >= 0:
            return sd.query_devices(indice)["hostapi"]

    except Exception:
        pass

    return None


def _mesmo_aparelho(nome_a, nome_b):
    # O MME corta o nome; se um é começo do outro, é o mesmo aparelho.
    menor, maior = sorted((nome_a, nome_b), key=len)

    return maior.startswith(menor)


def listar_dispositivos(entrada):
    """
    Devolve [(nome_exibido, indice)] com um item por aparelho real.
    Não inclui a opção "Padrão do Windows" — quem monta o select
    acrescenta essa no topo.
    """
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

        # Alguns nomes vêm com quebra de linha (um caminho de driver
        # real desta máquina tinha), o que quebraria a exibição.
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
                # Guarda o nome mais completo entre as variantes.
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

    # Rede de segurança: se o filtro tiver escondido tudo (uma máquina
    # onde só exista WDM-KS, por exemplo), é melhor mostrar a lista
    # crua do que um select vazio.
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
    """
    Nome guardado -> índice atual. Devolve None quando o aparelho não
    está mais conectado, e nesse caso quem chama volta para o padrão
    do sistema em vez de estourar.
    """
    if not nome_guardado:
        return None

    for nome, indice in listar_dispositivos(entrada):
        if _mesmo_aparelho(nome, nome_guardado):
            return indice

    return None


def aplicar_preferencias():
    """
    Lê o config.json e aplica a escolha em sd.default.device, que é o
    que TODOS os streams do projeto passam a usar: o microfone da
    chamada, a reprodução, o detector de palavra-chave e o cérebro
    reserva. Nenhum deles precisou ser alterado por causa disso.

    Chamado uma vez na inicialização (main.py) e de novo a cada troca
    no select. Nunca levanta exceção.
    """
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

        # True enquanto os selects estão sendo preenchidos, para o
        # sinal de mudança não salvar nada durante a montagem.
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

        # O ESTILO_GLOBAL da janela principal tem as regras comentadas
        # com cerquilha, o que em QSS mata a regra seguinte (ver
        # jarvis/ui/painel_console.py). Por isso o painel se estiliza
        # sozinho, igual o console.
        estilo = (
            "QComboBox#comboDispositivo {"
            "    min-height: 0px;"
            "    padding: 4px 8px;"
            "    font-size: 10px;"
            "}"
        )

        self.combo_microfone.setStyleSheet(estilo)
        self.combo_alto_falante.setStyleSheet(estilo)

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

    # Relê a lista de aparelhos e reaplica a seleção salva.
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

        # O detector de palavra-chave fica com o microfone aberto
        # entre as chamadas; sem reiniciá-lo, a troca só valeria na
        # próxima vez que o app abrisse. pausar() bloqueia até o
        # stream fechar de verdade, então não há dois handles no
        # mesmo aparelho (ver jarvis/pacotes/ativacao_voz/detector.py).
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
