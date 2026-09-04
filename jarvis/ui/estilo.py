# Identidade visual compartilhada por TODAS as janelas do app.
#
# Antes, só jarvis/ui/janela_principal.py tinha um QSS de verdade (e mesmo
# esse tinha um bug real: QSS não tem comentário de linha com "#" — só
# bloco no estilo CSS, "/* ... */". Cada linha comentada com "#" virava
# um SELETOR DE ID e engolia a regra seguinte inteira. Já estava medido
# em jarvis/ui/painel_console.py: das 16 regras do antigo ESTILO_GLOBAL,
# 13 estavam mortas por causa disso — é por isso que a janela sempre
# renderizou no tema escuro padrão do sistema em vez do visual branco
# que o código antigo descrevia. Corrigido aqui: todo comentário deste
# arquivo usa /* */.
#
# A paleta não é nova — é a que a esfera animada (jarvis/ui/visualizador_alfred.py)
# já usa (fundo quase preto QColor(3,3,5), gradiente em vermelho profundo/
# carmesim) e que o botão de chamada já usa (#b00020). As outras telas
# são elevadas até esse nível, não o contrário.
#
# Os hex abaixo são reexportados como constantes (não só embutidos na
# string QSS) porque jarvis/ui/painel_console.py e jarvis/ui/painel_dispositivos.py
# continuam se auto-estilizando (setStyleSheet no próprio widget, não
# pelo ESTILO_GLOBAL) — decisão de encapsulamento documentada nesses dois
# arquivos, mantida mesmo com o bug corrigido. Importar os tokens daqui
# evita duas fontes de verdade para a mesma cor.

# Fundo das janelas — igual ao QColor(3, 3, 5) do fundo da esfera.
FUNDO_JANELA = "#050406"

# Fundo de superfícies elevadas: caixas de texto, inputs, área de drop.
FUNDO_PAINEL = "#0d0a0c"

# Borda padrão (grená escuro) e borda em hover/foco (vermelho de acento).
BORDA = "#2a1014"
BORDA_FOCO = "#b00020"

# Texto principal e texto de apoio (rótulos, subtítulos).
TEXTO_PRIMARIO = "#ece6e7"
TEXTO_SECUNDARIO = "#8f8388"

# Vermelho de identidade do ALFRED — já usado no botão de chamada.
ACCENT = "#b00020"
ACCENT_HOVER = "#98001c"

# Vermelho mais vivo, mesmo tom dos anéis/núcleo da esfera — usado em
# destaques funcionais (valor do status), nunca decorativo.
ACCENT_BRILHO = "#ff3044"

# Fundo e hover dos botões secundários/terciários.
BOTAO_FUNDO = "#150c0e"
BOTAO_HOVER = "#22131a"
BOTAO_PRESSED = "#1a0e10"


# QSS aplicado por cada janela top-level (MainWindow, JanelaCamera,
# ChatWindow, EnvioArquivoWindow) no próprio setStyleSheet — cada uma
# delas é uma janela separada, não filha de MainWindow, então não herda
# o estilo dela automaticamente.
ESTILO_GLOBAL = """
/* Fundo padrão de qualquer janela/container. */
QMainWindow, QWidget, QDialog {
    background-color: #050406;
    color: #ece6e7;
    font-family: "Segoe UI";
}

/* Rótulos são transparentes por padrão — só pintam quando um
   objectName específico define o contrário (ex: statusValor, em chip). */
QLabel {
    background: transparent;
    color: #ece6e7;
}

/* Título da coluna de controles ("ALFRED"). O espaçamento entre letras
   não é feito aqui — QSS não suporta letter-spacing, só é possível via
   QFont em Python (ver jarvis/ui/janela_principal.py, mesma técnica já
   usada em jarvis/ui/visualizador_alfred.py). */
QLabel#titulo {
    color: #ece6e7;
    font-size: 18px;
    font-weight: 600;
}

/* Subtítulo — texto de apoio, discreto. */
QLabel#subtitulo {
    color: #8f8388;
    font-size: 10px;
}

/* Títulos de seção pequenos: "Status", "Registro de atividade",
   "Microfone", "Alto-falante", "Console". */
QLabel#statusTitulo {
    color: #8f8388;
    font-size: 11px;
    font-weight: 600;
}

/* Valor do status — vira um "chip" (fundo translúcido + borda), não só
   texto solto: é o único indicador de estado da coluna lateral, então
   ganha presença visual que é funcional, não decorativa. */
QLabel#statusValor {
    color: #ff3044;
    background-color: rgba(176, 0, 32, 0.14);
    border: 1px solid #b00020;
    border-radius: 4px;
    padding: 4px 0;
    font-size: 13px;
    font-weight: 600;
}

/* Botão padrão — usado como base por qualquer QPushButton sem
   objectName específico (ex: "Enviar" no chat, "Selecionar arquivo..."
   no envio de arquivo, "Limpar" no console). */
QPushButton {
    min-height: 40px;
    padding: 0 14px;
    color: #ece6e7;
    background-color: #150c0e;
    border: 1px solid #2a1014;
    border-radius: 4px;
    font-size: 11px;
}

QPushButton:hover {
    background-color: #22131a;
    border: 1px solid #b00020;
}

QPushButton:pressed {
    background-color: #1a0e10;
}

/* Botão primário — a chamada. Único vermelho sólido da interface,
   reservado pra ação mais importante da tela. */
QPushButton#botaoChamada {
    color: #ffffff;
    background-color: #b00020;
    border: 1px solid #8f001a;
    font-weight: 600;
}

QPushButton#botaoChamada:hover {
    background-color: #98001c;
}

QPushButton#botaoChamada[encerrando="true"] {
    color: #ffffff;
    background-color: #4a4a4a;
    border: 1px solid #3a3a3a;
}

/* Botão secundário — ações de visão (ANALISAR TELA/CÂMERA). Outline
   vermelho sobre fundo escuro: um degrau abaixo do botão primário. */
QPushButton#botaoVisao {
    color: #ece6e7;
    background-color: #0d0a0c;
    border: 1px solid #6e0016;
}

QPushButton#botaoVisao:hover {
    background-color: #150c0e;
    border: 1px solid #b00020;
    color: #ff3044;
}

/* Botão terciário — navegação secundária (CONFIGURAÇÕES, CHAT, CÂMERA
   AO VIVO, ENVIAR ARQUIVO). Mais discreto: borda grená neutra que só
   acende vermelho no hover, pra não competir com o fluxo principal. */
QPushButton#botaoNav {
    min-height: 34px;
    color: #8f8388;
    background-color: transparent;
    border: 1px solid #2a1014;
    font-size: 10px;
}

QPushButton#botaoNav:hover {
    color: #ece6e7;
    border: 1px solid #b00020;
    background-color: #0d0a0c;
}

/* Caixas de texto — registro de atividade, histórico do chat, etc. */
QTextEdit {
    color: #ece6e7;
    background-color: #0d0a0c;
    border: 1px solid #2a1014;
    border-radius: 3px;
    padding: 8px;
    font-family: "Consolas";
    font-size: 10px;
    selection-background-color: #b00020;
}

QTextEdit:focus {
    border: 1px solid #b00020;
}

/* Campo de texto de uma linha (o campo de mensagem do chat). */
QLineEdit {
    color: #ece6e7;
    background-color: #0d0a0c;
    border: 1px solid #2a1014;
    border-radius: 3px;
    padding: 6px 8px;
    font-size: 11px;
    selection-background-color: #b00020;
}

QLineEdit:focus {
    border: 1px solid #b00020;
}

/* Selects de microfone/alto-falante — só a cor base vem daqui;
   dimensão (min-height, padding, font-size) continua sendo ajustada
   localmente em jarvis/ui/painel_dispositivos.py. */
QComboBox {
    color: #ece6e7;
    background-color: #0d0a0c;
    border: 1px solid #2a1014;
    border-radius: 3px;
}

QComboBox:hover {
    border: 1px solid #b00020;
}

QComboBox QAbstractItemView {
    color: #ece6e7;
    background-color: #0d0a0c;
    border: 1px solid #2a1014;
    selection-background-color: #b00020;
    selection-color: #ffffff;
}

/* Caixas de diálogo padrão (ex: aviso de formato não suportado em
   jarvis/ui/janela_envio_arquivo.py). */
QMessageBox {
    background-color: #050406;
}

QMessageBox QLabel {
    color: #ece6e7;
}

/* Barra de rolagem — a padrão clara do sistema destoaria muito do
   fundo escuro em qualquer QTextEdit/QComboBox mais cheio. */
QScrollBar:vertical {
    background: #050406;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3a1319;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #b00020;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #050406;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #3a1319;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #b00020;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""
