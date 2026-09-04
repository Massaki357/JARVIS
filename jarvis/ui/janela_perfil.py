# Janela de perfis do jarvis — escolher, criar e editar perfil.
#
# Um PERFIL é um cenário de uso: um prompt de sistema próprio mais um
# subconjunto das ferramentas do projeto. A camada de dados
# (jarvis/nucleo/perfis/) já faz todo o trabalho de disco; esta janela
# só desenha e chama aquelas funções.
#
# TRÊS PÁGINAS NA MESMA JANELA, não três janelas: um QStackedWidget
# troca o conteúdo e a janela continua sendo a mesma. Assim o usuário
# não acumula janelas soltas na barra de tarefas, e o botão de voltar
# tem para onde voltar.
#
#     índice 0  PáginaInicial   select de perfis + criar + editar
#     índice 1  PáginaCriacao   criação por descrição em texto
#     índice 2  PáginaEdicao    ferramentas + prompt do perfil
#
# Fase 2 (esta): navegação entre as três páginas, o select ligado ao
# índice real, e a edição manual direta (ferramentas e prompt) já
# gravando de verdade pela camada de dados. A página de criação é só o
# esqueleto — quem a preenche é a Fase 3 (geração por IA).
#
# O que esta janela AINDA NÃO faz, e diz isso na cara do usuário em
# vez de fingir que faz: escolher um perfil aqui grava a preferência,
# mas a chamada ainda não a lê. Quem liga o perfil escolhido ao início
# da chamada é a Fase 5.
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QScrollArea,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.nucleo import perfis

# Identidade visual compartilhada (preto/vermelho) — esta janela é
# top-level, separada de MainWindow, então aplica o estilo nela mesma,
# igual a JanelaCamera/ChatWindow/EnvioArquivoWindow.
from jarvis.ui.estilo import (
    ACCENT_BRILHO,
    BORDA,
    ESTILO_GLOBAL,
    TEXTO_SECUNDARIO,
)

# Estilo das listas desta janela. Fica aqui, e não no ESTILO_GLOBAL,
# porque QListWidget só é usado nesta tela — mesmo princípio de
# encapsulamento de jarvis/ui/painel_console.py. A variante :disabled
# não é opcional: um seletor de ID ou uma regra local vence
# QListWidget:disabled, e sem ela a lista ficaria idêntica habilitada
# e desabilitada (ver testes/auditar_estilo_desabilitado.py).
_ESTILO_LISTA = (
    "QListWidget {"
    "  background-color: #0d0a0c;"
    "  border: 1px solid #2a1014;"
    "  border-radius: 3px;"
    "  font-family: 'Consolas';"
    "  font-size: 10px;"
    "}"
    "QListWidget::item { padding: 3px 4px; }"
    "QListWidget::item:selected {"
    "  background-color: #b00020;"
    "  color: #ffffff;"
    "}"
    "QListWidget:disabled {"
    "  color: #4d4348;"
    "  background-color: #0a0709;"
    "  border: 1px solid #1a0b0e;"
    "}"
)


# Índices das páginas dentro do QStackedWidget. Constantes com nome
# em vez de 0/1/2 soltos no meio do código.
PAGINA_INICIAL = 0
PAGINA_CRIACAO = 1
PAGINA_EDICAO = 2
PAGINA_CONFIRMACAO = 3

# Páginas em que voltar descarta trabalho do usuário e por isso pedem
# confirmação antes. A de criação não entra: lá nada foi criado ainda,
# e o texto digitado continua no campo se ele voltar a entrar.
_PAGINAS_QUE_PERGUNTAM_AO_VOLTAR = (PAGINA_EDICAO, PAGINA_CONFIRMACAO)


class JanelaPerfil(QWidget):

    def __init__(self, ao_fechar=None):
        super().__init__()

        # Chamado quando a janela fecha — mesmo padrão de
        # JanelaCamera/ChatWindow/EnvioArquivoWindow, pra main.py
        # saber que ela não existe mais e limpar a referência dele.
        self._ao_fechar = ao_fechar

        # Slug do perfil sendo editado na página de edição. None fora
        # dela.
        self._slug_em_edicao = None

        # True enquanto a edição aberta for a de um perfil cuja lista
        # de ferramentas é imutável (hoje, só o perfil padrão).
        self._ferramentas_travadas = False

        # Sugestão devolvida pela IA, esperando confirmação. None fora
        # da página de confirmação.
        self._sugestao = None

        # Thread da chamada ao modelo. Guardada como atributo pra não
        # ser coletada pelo garbage collector enquanto ainda roda.
        self._gerador = None

        self.setWindowTitle("Perfil - jarvis")
        self.resize(780, 780)
        self.setMinimumSize(640, 600)
        self.setStyleSheet(ESTILO_GLOBAL)

        # Garante que o perfil padrão existe antes de qualquer
        # listagem — numa máquina onde a pasta dados/perfis/ ainda não
        # foi criada, é isto que a cria. Idempotente.
        try:
            perfis.garantir_perfil_padrao()

        except Exception as erro:
            print(f"[perfis] Não consegui garantir o perfil padrão: {erro}")

        self._paginas = QStackedWidget()

        self._paginas.addWidget(self._construir_pagina_inicial())
        self._paginas.addWidget(self._construir_pagina_criacao())
        self._paginas.addWidget(self._construir_pagina_edicao())
        self._paginas.addWidget(self._construir_pagina_confirmacao())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(self._paginas)

        self.recarregar_perfis()

    # ============================================================
    # Peças visuais reaproveitadas pelas três páginas
    # ============================================================

    def _titulo(self, texto):
        rotulo = QLabel(texto)
        rotulo.setObjectName("titulo")

        # QSS não tem letter-spacing; só dá pra fazer via QFont, mesma
        # técnica já usada em jarvis/ui/janela_principal.py.
        fonte = QFont("Segoe UI", 13)
        fonte.setWeight(QFont.Weight.DemiBold)
        fonte.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        rotulo.setFont(fonte)

        return rotulo

    def _rotulo_secao(self, texto):
        rotulo = QLabel(texto)
        rotulo.setObjectName("statusTitulo")

        return rotulo

    def _texto_apoio(self, texto):
        rotulo = QLabel(texto)
        rotulo.setWordWrap(True)
        rotulo.setStyleSheet(
            f"color: {TEXTO_SECUNDARIO}; font-size: 10px;"
        )

        return rotulo

    def _barra_voltar(self, titulo):
        """
        Cabeçalho das páginas internas: botão de voltar no canto
        superior esquerdo, título ao lado. Volta SEM salvar nada — é
        por isso que a página de edição pergunta antes, e a de criação
        não precisa perguntar (nada foi criado ainda).
        """
        botao = QPushButton("← VOLTAR")
        botao.setObjectName("botaoNav")
        botao.setFixedWidth(110)

        # O lambda NÃO é decorativo: QPushButton.clicked carrega um
        # argumento bool (checked, sempre False num botão não
        # checável), e conectar o método direto faria o Qt passar esse
        # False como "perguntar" — a confirmação de sair sem salvar
        # nunca apareceria. Confirmado na prática antes de escrever
        # isto, não deduzido da documentação.
        botao.clicked.connect(
            lambda: self._voltar_para_inicial()
        )

        linha = QHBoxLayout()
        linha.setSpacing(12)
        linha.addWidget(botao)
        linha.addWidget(self._titulo(titulo))
        linha.addStretch()

        return linha, botao

    # ============================================================
    # Página inicial
    # ============================================================

    def _construir_pagina_inicial(self):
        pagina = QWidget()

        layout = QVBoxLayout(pagina)
        layout.setSpacing(10)

        layout.addWidget(self._titulo("PERFIL"))

        layout.addWidget(
            self._texto_apoio(
                "Cada perfil tem um prompt de sistema próprio e um "
                "conjunto de ferramentas habilitadas. O perfil "
                "escolhido aqui vale para a PRÓXIMA chamada — trocar "
                "de perfil nunca afeta uma chamada já em andamento."
            )
        )

        layout.addSpacing(10)

        layout.addWidget(self._rotulo_secao("PERFIL ATIVO"))

        self._select_perfis = QComboBox()
        self._select_perfis.setMinimumHeight(34)
        self._select_perfis.currentIndexChanged.connect(
            self._ao_trocar_perfil_selecionado
        )

        layout.addWidget(self._select_perfis)

        self._resumo_perfil = self._texto_apoio("")
        layout.addWidget(self._resumo_perfil)

        layout.addSpacing(14)

        self._btn_criar = QPushButton("CRIAR PERFIL")
        self._btn_criar.setObjectName("botaoVisao")
        self._btn_criar.clicked.connect(self._abrir_pagina_criacao)

        self._btn_editar = QPushButton("EDITAR PERFIL")
        self._btn_editar.setObjectName("botaoNav")
        self._btn_editar.clicked.connect(self._abrir_pagina_edicao)

        linha_botoes = QHBoxLayout()
        linha_botoes.setSpacing(10)
        linha_botoes.addWidget(self._btn_criar)
        linha_botoes.addWidget(self._btn_editar)

        layout.addLayout(linha_botoes)

        layout.addStretch()

        # Aviso honesto: nesta fase a escolha é gravada mas ainda não
        # muda a chamada. Melhor dizer do que deixar o usuário achar
        # que trocou o comportamento do jarvis e não trocou.
        self._aviso_fase = self._texto_apoio(
            "A escolha já é gravada em config.json, mas a chamada "
            "ainda não a usa: a integração com o início da chamada "
            "é a próxima etapa."
        )

        layout.addWidget(self._aviso_fase)

        return pagina

    def _ao_trocar_perfil_selecionado(self):
        """
        Grava o perfil escolhido como o ativo da próxima chamada e
        atualiza o resumo abaixo do select.
        """
        slug = self.slug_selecionado()

        if not slug:
            self._resumo_perfil.setText("")
            return

        try:
            perfil = perfis.carregar_perfil(slug)

        except (FileNotFoundError, ValueError) as erro:
            self._resumo_perfil.setText(f"Perfil ilegível: {erro}")
            return

        if perfil["ferramentas"] is perfis.TODAS_AS_FERRAMENTAS:
            descricao_ferramentas = (
                "todas as ferramentas registradas "
                f"({len(perfis.ferramentas_efetivas(perfil))} hoje)"
            )

        else:
            descricao_ferramentas = (
                f"{len(perfil['ferramentas'])} ferramentas"
            )

        partes = [descricao_ferramentas]

        if perfil["descricao"]:
            partes.append(perfil["descricao"])

        self._resumo_perfil.setText(" — ".join(partes))

        # Só grava se realmente mudou, pra não reescrever o config.json
        # a cada repopulação do select.
        if perfis.perfil_ativo() != slug:
            try:
                perfis.definir_perfil_ativo(slug)

            except FileNotFoundError:
                pass

    def slug_selecionado(self):
        dados = self._select_perfis.currentData()

        return dados if dados else None

    def recarregar_perfis(self, slug_para_selecionar=None):
        """
        Repopula o select a partir do índice. Mantém a seleção atual
        (ou seleciona o slug pedido, usado depois de criar um perfil).
        """
        alvo = (
            slug_para_selecionar
            or self.slug_selecionado()
            or perfis.perfil_ativo()
        )

        # Bloqueia o sinal durante a repopulação: senão cada
        # addItem dispararia _ao_trocar_perfil_selecionado e gravaria
        # um perfil ativo intermediário no config.json.
        self._select_perfis.blockSignals(True)
        self._select_perfis.clear()

        try:
            lista = perfis.listar_perfis()

        except Exception as erro:
            lista = []
            print(f"[perfis] Não consegui listar os perfis: {erro}")

        for entrada in lista:
            rotulo = entrada["nome"]

            if entrada["padrao"]:
                rotulo += "  (padrão)"

            self._select_perfis.addItem(rotulo, entrada["slug"])

        indice = self._select_perfis.findData(alvo)

        if indice >= 0:
            self._select_perfis.setCurrentIndex(indice)

        self._select_perfis.blockSignals(False)

        self._btn_editar.setEnabled(bool(lista))

        self._ao_trocar_perfil_selecionado()

    # ============================================================
    # Página de criação (esqueleto — conteúdo funcional na Fase 3)
    # ============================================================

    def _construir_pagina_criacao(self):
        pagina = QWidget()

        layout = QVBoxLayout(pagina)
        layout.setSpacing(10)

        barra, _botao = self._barra_voltar("CRIAR PERFIL")
        layout.addLayout(barra)

        layout.addSpacing(8)

        layout.addWidget(
            self._texto_apoio(
                "Descreva em texto livre o que o jarvis deve ser neste "
                "perfil. A IA escolhe as ferramentas e escreve o "
                "prompt de sistema — você confere tudo na etapa "
                "seguinte antes de qualquer coisa ser gravada."
            )
        )

        layout.addSpacing(6)

        layout.addWidget(self._rotulo_secao("DESCRIÇÃO DO PERFIL"))

        self._campo_descricao = QTextEdit()
        self._campo_descricao.setAcceptRichText(False)
        self._campo_descricao.setPlaceholderText(
            "Ex.: Agora você vai agir como um consultor de "
            "investimentos, focado em ações da bolsa. Não quero que "
            "você mexa nos meus arquivos."
        )

        layout.addWidget(self._campo_descricao, stretch=1)

        self._btn_gerar = QPushButton("GERAR PERFIL")
        self._btn_gerar.setObjectName("botaoVisao")
        self._btn_gerar.clicked.connect(self._gerar_perfil)

        layout.addWidget(self._btn_gerar)

        self._status_criacao = self._texto_apoio("")
        layout.addWidget(self._status_criacao)

        return pagina

    def _gerar_perfil(self):
        """
        Dispara a geração numa thread separada.

        A chamada ao modelo é uma requisição HTTP com retentativa —
        pode levar vários segundos. Feita aqui, na thread da GUI, ela
        congelaria a janela inteira. O worker abaixo só emite Signal,
        nunca toca em widget, seguindo a mesma disciplina de thread do
        GeminiLiveWorker.
        """
        descricao = self._campo_descricao.toPlainText().strip()

        if not descricao:
            self._avisar(
                "Descrição vazia",
                "Descreva o perfil antes de gerar.",
            )
            return

        self._btn_gerar.setEnabled(False)
        self._campo_descricao.setEnabled(False)
        self._status_criacao.setText(
            "Consultando o modelo... isso pode levar alguns segundos."
        )

        self._gerador = _GeradorDePerfil(descricao)
        self._gerador.terminou.connect(self._ao_terminar_geracao)
        self._gerador.start()

    def _ao_terminar_geracao(self, sucesso, resultado):
        self._btn_gerar.setEnabled(True)
        self._campo_descricao.setEnabled(True)
        self._status_criacao.setText("")

        if not sucesso:
            self._avisar("Não consegui gerar o perfil", str(resultado))
            return

        self._mostrar_confirmacao(resultado)

    def _abrir_pagina_criacao(self):
        self._paginas.setCurrentIndex(PAGINA_CRIACAO)

    # ============================================================
    # Página de confirmação (o que a IA sugeriu)
    # ============================================================

    def _construir_pagina_confirmacao(self):
        pagina = QWidget()

        layout = QVBoxLayout(pagina)
        layout.setSpacing(8)

        barra, _botao = self._barra_voltar("CONFIRMAR PERFIL")
        layout.addLayout(barra)

        layout.addWidget(
            self._texto_apoio(
                "Nada foi gravado ainda. Confira o que a IA sugeriu, "
                "aprove as ferramentas sensíveis que quiser liberar, e "
                "só então crie o perfil."
            )
        )

        layout.addWidget(self._rotulo_secao("NOME DE EXIBIÇÃO"))

        self._campo_nome_novo = QLineEdit()
        layout.addWidget(self._campo_nome_novo)

        # Só ganha texto quando o modelo inventa um nome de ferramenta.
        self._aviso_inventadas = self._texto_apoio("")
        self._aviso_inventadas.setStyleSheet(
            f"color: {ACCENT_BRILHO}; font-size: 10px;"
        )
        layout.addWidget(self._aviso_inventadas)

        self._rotulo_comuns = self._rotulo_secao("")
        layout.addWidget(self._rotulo_comuns)

        self._lista_comuns = QListWidget()
        self._lista_comuns.setMaximumHeight(110)
        self._lista_comuns.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self._lista_comuns.setStyleSheet(_ESTILO_LISTA)
        layout.addWidget(self._lista_comuns)

        self._rotulo_sensiveis = self._rotulo_secao("")
        layout.addWidget(self._rotulo_sensiveis)

        self._aviso_sensiveis = self._texto_apoio("")
        layout.addWidget(self._aviso_sensiveis)

        self._lista_sensiveis = QListWidget()
        self._lista_sensiveis.setMaximumHeight(150)
        self._lista_sensiveis.setStyleSheet(_ESTILO_LISTA)
        layout.addWidget(self._lista_sensiveis)

        layout.addWidget(
            self._rotulo_secao("PROMPT DE SISTEMA GERADO")
        )

        self._editor_prompt_novo = QTextEdit()
        self._editor_prompt_novo.setAcceptRichText(False)
        layout.addWidget(self._editor_prompt_novo, stretch=1)

        self._btn_criar_confirmado = QPushButton("CRIAR PERFIL")
        self._btn_criar_confirmado.setObjectName("botaoVisao")
        self._btn_criar_confirmado.clicked.connect(
            self._criar_perfil_confirmado
        )

        layout.addWidget(self._btn_criar_confirmado)

        return pagina

    def _mostrar_confirmacao(self, sugestao):
        self._sugestao = sugestao

        self._campo_nome_novo.setText(sugestao["nome"])
        self._editor_prompt_novo.setPlainText(
            sugestao["prompt_sistema"]
        )

        inventadas = sugestao.get("inexistentes") or []

        if inventadas:
            # Nome inventado nunca entra no perfil (a validação já o
            # descartou), mas o usuário precisa saber que aconteceu:
            # um modelo inventando ferramenta é motivo pra olhar o
            # resto da sugestão com mais atenção.
            self._aviso_inventadas.setText(
                "A IA citou ferramenta que não existe no projeto e "
                f"ela foi descartada: {', '.join(inventadas)}"
            )

        else:
            self._aviso_inventadas.setText("")

        comuns, sensiveis = perfis.separar(sugestao["ferramentas"])

        self._rotulo_comuns.setText(
            f"FERRAMENTAS COMUNS ({len(comuns)}) — ENTRAM DIRETO"
        )

        self._lista_comuns.clear()

        for nome in comuns:
            linha = QListWidgetItem(
                f"{nome}  —  {perfis.resumo_de(nome)}"
            )
            linha.setData(Qt.ItemDataRole.UserRole, nome)

            self._lista_comuns.addItem(linha)

        if not comuns:
            self._lista_comuns.addItem(QListWidgetItem("(nenhuma)"))

        self._rotulo_sensiveis.setText(
            f"FERRAMENTAS SENSÍVEIS ({len(sensiveis)}) — "
            "PRECISAM DA SUA APROVAÇÃO"
        )

        self._aviso_sensiveis.setText(
            "Marque uma por uma o que este perfil pode fazer. O que "
            "ficar desmarcado NÃO entra no perfil."
            if sensiveis
            else "A IA não escolheu nenhuma ferramenta sensível."
        )

        self._lista_sensiveis.clear()

        for nome in sensiveis:
            item = QListWidgetItem(
                f"{nome}  —  {perfis.motivo_de(nome)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, nome)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )

            # DESMARCADA por padrão, sempre. É a regra inteira desta
            # tela: ferramenta sensível nunca entra sozinha, nem
            # quando a IA pediu.
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip(perfis.resumo_de(nome))

            self._lista_sensiveis.addItem(item)

        self._paginas.setCurrentIndex(PAGINA_CONFIRMACAO)

    def _sensiveis_aprovadas(self):
        aprovadas = []

        for indice in range(self._lista_sensiveis.count()):
            item = self._lista_sensiveis.item(indice)

            if item.checkState() != Qt.CheckState.Checked:
                continue

            nome = item.data(Qt.ItemDataRole.UserRole)

            if nome:
                aprovadas.append(nome)

        return aprovadas

    def _criar_perfil_confirmado(self):
        if not self._sugestao:
            return

        nome = self._campo_nome_novo.text().strip()

        if not nome:
            self._avisar(
                "Nome vazio",
                "O perfil precisa de um nome de exibição.",
            )
            return

        comuns, _sensiveis = perfis.separar(
            self._sugestao["ferramentas"]
        )

        escolhidas = comuns + self._sensiveis_aprovadas()

        try:
            criado = perfis.criar_perfil(
                nome=nome,
                prompt_sistema=self._editor_prompt_novo.toPlainText(),
                ferramentas=escolhidas,
                descricao=self._sugestao.get("descricao", ""),
            )

        except (ValueError, OSError) as erro:
            self._avisar("Não consegui criar o perfil", str(erro))
            return

        self._sugestao = None
        self._campo_descricao.clear()

        self._voltar_para_inicial(perguntar=False)
        self.recarregar_perfis(slug_para_selecionar=criado["slug"])

    # ============================================================
    # Página de edição
    # ============================================================

    def _construir_pagina_edicao(self):
        pagina = QWidget()

        layout = QVBoxLayout(pagina)
        layout.setSpacing(8)

        barra, _botao = self._barra_voltar("EDITAR PERFIL")
        layout.addLayout(barra)

        self._rotulo_editando = self._texto_apoio("")
        layout.addWidget(self._rotulo_editando)

        layout.addSpacing(6)

        layout.addWidget(self._rotulo_secao("NOME DE EXIBIÇÃO"))

        self._campo_nome = QLineEdit()
        layout.addWidget(self._campo_nome)

        layout.addSpacing(6)

        # --- ferramentas ---
        #
        # A lista mostra TODAS as ferramentas do projeto com caixa de
        # marcação, não só as que o perfil já tem. Sem isso o usuário
        # precisaria decorar o que existe para poder acrescentar —
        # marcar e desmarcar contra o catálogo inteiro é o que torna a
        # edição manual utilizável.
        self._rotulo_ferramentas = self._rotulo_secao(
            "FERRAMENTAS DO PERFIL"
        )
        layout.addWidget(self._rotulo_ferramentas)

        self._aviso_ferramentas = self._texto_apoio("")
        layout.addWidget(self._aviso_ferramentas)

        self._lista_ferramentas = QListWidget()
        self._lista_ferramentas.setStyleSheet(_ESTILO_LISTA)
        self._lista_ferramentas.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self._lista_ferramentas.itemChanged.connect(
            self._ao_marcar_ferramenta
        )

        # Altura mínima real: são 61 ferramentas mais 16 cabeçalhos de
        # categoria. Sem isto o layout espremia a lista em duas linhas
        # visíveis e dava todo o espaço ao editor de prompt —
        # conferido num print da janela renderizada, não no papel.
        self._lista_ferramentas.setMinimumHeight(230)

        # Sem isto, o resumo longo de algumas ferramentas força uma
        # barra de rolagem horizontal e o usuário teria que arrastar
        # a lista de lado para ler. Cortar com reticências é melhor:
        # o nome, que é o que identifica a ferramenta, vem primeiro.
        self._lista_ferramentas.setTextElideMode(
            Qt.TextElideMode.ElideRight
        )
        self._lista_ferramentas.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        layout.addWidget(self._lista_ferramentas, stretch=3)

        layout.addSpacing(10)

        # --- prompt ---
        layout.addWidget(self._rotulo_secao("PROMPT DE SISTEMA"))

        self._editor_prompt = QTextEdit()
        self._editor_prompt.setAcceptRichText(False)
        self._editor_prompt.setPlaceholderText(
            "Prompt de sistema deste perfil..."
        )

        self._editor_prompt.setMinimumHeight(120)

        layout.addWidget(self._editor_prompt, stretch=2)

        layout.addWidget(
            self._texto_apoio(
                "Linhas começando com ## são só títulos de navegação: "
                "não são enviadas ao modelo."
            )
        )

        self._btn_salvar = QPushButton("SALVAR")
        self._btn_salvar.setObjectName("botaoVisao")
        self._btn_salvar.clicked.connect(self._salvar_edicao)

        layout.addWidget(self._btn_salvar)

        # --- apagar ---
        #
        # Fica no rodapé, separado do SALVAR por uma divisória, e não
        # na página inicial ao lado de CRIAR/EDITAR: aqui o usuário já
        # abriu o perfil e está vendo o conteúdo dele. Na tela
        # anterior, apagar ficaria a um clique do select, sem ele ter
        # visto o que está apagando.
        #
        # Estilo próprio (botaoPerigo), nunca o vermelho de identidade
        # do app — esse é do INICIAR CHAMADA e do CRIAR PERFIL, ações
        # que devem ser fáceis de achar. Apagar não compete com elas.
        # QFrame com "color:" não pinta linha nenhuma no QSS — o que
        # desenha é altura fixa mais background-color.
        divisoria = QFrame()
        divisoria.setFixedHeight(1)
        divisoria.setStyleSheet(f"background-color: {BORDA};")

        layout.addSpacing(10)
        layout.addWidget(divisoria)
        layout.addSpacing(6)

        self._btn_apagar = QPushButton("APAGAR ESTE PERFIL")
        self._btn_apagar.setObjectName("botaoPerigo")
        self._btn_apagar.clicked.connect(self._apagar_perfil_atual)

        layout.addWidget(self._btn_apagar)

        self._aviso_apagar = self._texto_apoio("")
        layout.addWidget(self._aviso_apagar)

        # Esta página tem conteúdo demais para caber numa janela
        # pequena: a soma das alturas mínimas (lista de 61
        # ferramentas + editor de prompt + os dois botões do rodapé)
        # passa da altura útil, e o Qt resolve isso SOBREPONDO widgets
        # em vez de reclamar — o rótulo "PROMPT DE SISTEMA" ficava 7px
        # POR BAIXO da lista, medido na geometria da janela real, não
        # percebido no olho.
        #
        # Rolagem resolve de uma vez e para qualquer tamanho de
        # janela, inclusive o mínimo. As outras três páginas cabem
        # sem isto e ficaram como estavam.
        area = QScrollArea()
        area.setWidget(pagina)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; }")

        return area

    def _abrir_pagina_edicao(self):
        slug = self.slug_selecionado()

        if not slug:
            return

        try:
            perfil = perfis.carregar_perfil(slug)

        except (FileNotFoundError, ValueError) as erro:
            self._avisar("Não consegui abrir o perfil", str(erro))
            self.recarregar_perfis()
            return

        self._slug_em_edicao = perfil["slug"]

        self._rotulo_editando.setText(
            f"Pasta: dados/perfis/{perfil['slug']}/"
        )

        self._campo_nome.setText(perfil["nome"])
        self._editor_prompt.setPlainText(perfil["prompt_sistema"])

        # A lista de ferramentas do perfil padrão é IMUTÁVEL (ver
        # perfis.ferramentas_editaveis()): ele representa o jarvis
        # completo, e congelar o curinga "todas" numa lista fixa faria
        # todo pacote novo nascer desligado justamente no perfil que
        # deveria ter tudo. Aqui os controles são desabilitados para
        # explicar isso; quem GARANTE é a camada de dados, que recusa
        # a alteração venha ela de onde vier.
        self._ferramentas_travadas = not perfis.ferramentas_editaveis(
            perfil
        )

        self._montar_lista_ferramentas(perfil)

        self._btn_apagar.setEnabled(not perfil["padrao"])

        self._aviso_apagar.setText(
            "O perfil padrão não pode ser apagado."
            if perfil["padrao"]
            else "Apaga a pasta do perfil. Não tem como voltar."
        )

        self._paginas.setCurrentIndex(PAGINA_EDICAO)

    def _montar_lista_ferramentas(self, perfil):
        """
        Preenche a lista com TODAS as ferramentas do projeto,
        agrupadas por categoria, marcando as que o perfil já tem.
        """
        marcadas = set(perfis.ferramentas_efetivas(perfil))

        # Popular a lista dispara itemChanged em cada setCheckState;
        # sem bloquear, o contador se atualizaria dezenas de vezes à
        # toa durante a montagem.
        self._lista_ferramentas.blockSignals(True)
        self._lista_ferramentas.clear()

        categoria_anterior = None

        for item in perfis.catalogo_completo():
            if item["rotulo_categoria"] != categoria_anterior:
                categoria_anterior = item["rotulo_categoria"]

                cabecalho = QListWidgetItem(
                    f"── {categoria_anterior} ──"
                )
                cabecalho.setFlags(Qt.ItemFlag.NoItemFlags)
                cabecalho.setForeground(Qt.GlobalColor.darkGray)

                self._lista_ferramentas.addItem(cabecalho)

            self._lista_ferramentas.addItem(
                self._item_ferramenta(item, marcadas)
            )

        self._lista_ferramentas.blockSignals(False)

        self._lista_ferramentas.setEnabled(
            not self._ferramentas_travadas
        )

        if self._ferramentas_travadas:
            self._aviso_ferramentas.setText(
                "As ferramentas do perfil padrão não podem ser "
                "alteradas: ele é o jarvis completo e precisa "
                "continuar valendo para TODAS as ferramentas "
                "registradas, inclusive as que forem adicionadas ao "
                "projeto depois. Para um subconjunto, crie um perfil "
                "novo. O nome e o prompt abaixo continuam editáveis."
            )

        else:
            self._aviso_ferramentas.setText(
                "Marque o que este perfil pode usar. As em vermelho "
                "são sensíveis (passe o mouse para ver o motivo); as "
                "em cinza são obrigatórias e não podem ser "
                "desmarcadas."
            )

        self._atualizar_contagem_ferramentas()

    def _item_ferramenta(self, entrada, marcadas):
        nome = entrada["nome"]
        obrigatoria = nome in perfis.FERRAMENTAS_SEMPRE_ATIVAS

        item = QListWidgetItem(f"{nome}  —  {entrada['resumo']}")
        item.setData(Qt.ItemDataRole.UserRole, nome)

        if obrigatoria:
            # Marcada e sem poder desmarcar: sem elas o usuário fica
            # sem como encerrar a chamada por voz. A trava real está
            # em normalizar_ferramentas(), que as recoloca de
            # qualquer jeito; aqui é só para não oferecer uma caixa
            # que não obedece.
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setCheckState(Qt.CheckState.Checked)
            item.setForeground(Qt.GlobalColor.gray)
            item.setToolTip(
                "Ferramenta obrigatória — todo perfil tem esta."
            )

            return item

        item.setFlags(
            item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(
            Qt.CheckState.Checked
            if nome in marcadas
            else Qt.CheckState.Unchecked
        )

        # Sensível não é bloqueada na edição manual: marcar a caixa
        # você mesmo JÁ é a aprovação explícita — a confirmação item
        # a item da Fase 3 existe porque lá quem escolheu foi a IA,
        # não você. O destaque em vermelho é para você saber o que
        # está ligando.
        if perfis.e_sensivel(nome):
            item.setForeground(QColor(ACCENT_BRILHO))
            item.setToolTip(f"Sensível — {perfis.motivo_de(nome)}")

        # Cor por item (setForeground) VENCE o QSS, então a regra
        # QListWidget:disabled não apagaria este vermelho e a lista
        # travada ficaria com a mesma cara da editável — a mesma
        # família do bug de especificidade que
        # testes/auditar_estilo_desabilitado.py existe para pegar.
        # Com a lista travada, todo item vai para cinza.
        if self._ferramentas_travadas:
            item.setForeground(Qt.GlobalColor.gray)

        return item

    def _ao_marcar_ferramenta(self, _item):
        self._atualizar_contagem_ferramentas()

    def _atualizar_contagem_ferramentas(self):
        marcadas = self._ferramentas_marcadas()
        total = len(perfis.nomes_disponiveis())
        sensiveis = sum(
            1 for nome in marcadas if perfis.e_sensivel(nome)
        )

        texto = f"FERRAMENTAS DO PERFIL — {len(marcadas)} DE {total}"

        if sensiveis:
            texto += f" ({sensiveis} SENSÍVEIS)"

        self._rotulo_ferramentas.setText(texto)

    def _ferramentas_marcadas(self):
        marcadas = []

        for indice in range(self._lista_ferramentas.count()):
            item = self._lista_ferramentas.item(indice)
            nome = item.data(Qt.ItemDataRole.UserRole)

            if not nome:
                continue

            if item.checkState() == Qt.CheckState.Checked:
                marcadas.append(nome)

        return marcadas

    def _salvar_edicao(self):
        if not self._slug_em_edicao:
            return

        nome = self._campo_nome.text().strip()

        if not nome:
            self._avisar(
                "Nome vazio",
                "O perfil precisa de um nome de exibição.",
            )
            return

        try:
            if self._ferramentas_travadas:
                # Sem o argumento "ferramentas", editar_perfil mantém
                # o que já estava lá — no padrão, o curinga "todas".
                # Mandar a lista renderizada na tela seria justamente
                # congelar o curinga, que é o que a trava impede.
                perfis.editar_perfil(
                    self._slug_em_edicao,
                    nome=nome,
                    prompt_sistema=self._editor_prompt.toPlainText(),
                )

            else:
                perfis.editar_perfil(
                    self._slug_em_edicao,
                    nome=nome,
                    prompt_sistema=self._editor_prompt.toPlainText(),
                    ferramentas=self._ferramentas_marcadas(),
                )

        except (FileNotFoundError, ValueError, OSError) as erro:
            self._avisar("Não consegui salvar", str(erro))
            return

        salvo = self._slug_em_edicao

        # recarregar_perfis relê o índice, que editar_perfil acabou de
        # regravar — é assim que um nome de exibição trocado aparece
        # no select sem precisar fechar a janela.
        self._voltar_para_inicial(perguntar=False)
        self.recarregar_perfis(slug_para_selecionar=salvo)

    def _apagar_perfil_atual(self):
        """
        Apaga o perfil aberto na edição, depois de uma confirmação
        que obriga a ler.

        O diálogo traz o NOME do perfil e o caminho da pasta no texto,
        o botão diz "Apagar perfil" em vez de "Sim" (quem clica por
        reflexo no botão afirmativo precisa ler para achá-lo), e o
        foco começa em Cancelar.
        """
        if not self._slug_em_edicao:
            return

        try:
            perfil = perfis.carregar_perfil(self._slug_em_edicao)

        except (FileNotFoundError, ValueError) as erro:
            self._avisar("Não consegui abrir o perfil", str(erro))
            return

        caixa = QMessageBox(self)
        caixa.setWindowTitle("Apagar perfil")
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setText(f"Apagar o perfil \"{perfil['nome']}\"?")
        caixa.setInformativeText(
            f"A pasta dados/perfis/{perfil['slug']}/ e o prompt de "
            "sistema dele serão apagados. Não tem como desfazer."
        )

        botao_apagar = caixa.addButton(
            "Apagar perfil",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        botao_cancelar = caixa.addButton(
            "Cancelar",
            QMessageBox.ButtonRole.RejectRole,
        )

        caixa.setDefaultButton(botao_cancelar)
        caixa.exec()

        if caixa.clickedButton() is not botao_apagar:
            return

        try:
            perfis.apagar_perfil(perfil["slug"])

        except (FileNotFoundError, ValueError, OSError) as erro:
            self._avisar("Não consegui apagar", str(erro))
            return

        # apagar_perfil já devolveu a preferência para o padrão se o
        # perfil apagado era o ativo (ver armazenamento.apagar_perfil).
        self._voltar_para_inicial(perguntar=False)
        self.recarregar_perfis()

    def _voltar_para_inicial(self, perguntar=True):
        """
        Volta para a página inicial SEM salvar. Vindo da edição,
        confirma antes — o usuário pode ter digitado no prompt e o
        botão de voltar fica bem ao lado do de salvar.
        """
        pode_perder_trabalho = (
            self._paginas.currentIndex()
            in _PAGINAS_QUE_PERGUNTAM_AO_VOLTAR
        )

        if perguntar and pode_perder_trabalho:
            resposta = QMessageBox.question(
                self,
                "Voltar sem salvar",
                "As alterações que você fez neste perfil serão "
                "descartadas. Voltar mesmo assim?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if resposta != QMessageBox.StandardButton.Yes:
                return

        self._slug_em_edicao = None
        self._paginas.setCurrentIndex(PAGINA_INICIAL)

    def _avisar(self, titulo, texto):
        QMessageBox.information(self, titulo, texto)

    def closeEvent(self, evento):
        if self._ao_fechar:
            self._ao_fechar()

        super().closeEvent(evento)


class _GeradorDePerfil(QThread):
    """
    Chama o modelo numa thread separada e devolve o resultado por
    Signal.

    Existe por um motivo só: perfis.gerar_sugestao() é uma requisição
    HTTP com até três tentativas e espera crescente entre elas —
    executada na thread da GUI, a janela congelaria durante todo esse
    tempo, inclusive o botão de voltar.

    Segue a mesma disciplina de thread do GeminiLiveWorker: NUNCA toca
    num widget, só emite Signal. Quem mexe na interface é o slot do
    outro lado, que roda na thread da GUI.
    """

    # (sucesso, resultado) — resultado é o dict da sugestão quando deu
    # certo, ou a mensagem de erro em português quando não deu. O
    # segundo parâmetro é `object` porque carrega um dict num caso e
    # uma str no outro.
    terminou = Signal(bool, object)

    def __init__(self, descricao):
        super().__init__()

        self._descricao = descricao

    def run(self):
        try:
            sucesso, resultado = perfis.gerar_sugestao(self._descricao)

        except Exception as erro:
            # gerar_sugestao já promete não levantar, mas uma thread
            # que morre com exceção não avisaria ninguém e a tela
            # ficaria travada em "Consultando o modelo..." para
            # sempre. A rede de segurança custa três linhas.
            sucesso, resultado = False, f"Erro inesperado: {erro}"

        self.terminou.emit(sucesso, resultado)
