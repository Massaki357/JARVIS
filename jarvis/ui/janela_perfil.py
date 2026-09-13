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

from jarvis.ui.estilo import (
    ACCENT_BRILHO,
    BORDA,
    ESTILO_GLOBAL,
    TEXTO_SECUNDARIO,
)

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


PAGINA_INICIAL = 0
PAGINA_CRIACAO = 1
PAGINA_EDICAO = 2
PAGINA_CONFIRMACAO = 3

_PAGINAS_QUE_PERGUNTAM_AO_VOLTAR = (PAGINA_EDICAO, PAGINA_CONFIRMACAO)


class JanelaPerfil(QWidget):
    def __init__(self, ao_fechar=None):
        super().__init__()

        self._ao_fechar = ao_fechar

        self._slug_em_edicao = None

        self._ferramentas_travadas = False

        self._sugestao = None

        self._nomes_do_cerebro = set()
        self._rotulo_cerebro = ""

        self._gerador = None

        self.setWindowTitle("Perfil - jarvis")
        self.resize(780, 780)
        self.setMinimumSize(640, 600)
        self.setStyleSheet(ESTILO_GLOBAL)

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

    def _titulo(self, texto):
        rotulo = QLabel(texto)
        rotulo.setObjectName("titulo")

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
        botao = QPushButton("← VOLTAR")
        botao.setObjectName("botaoNav")
        botao.setFixedWidth(110)

        botao.clicked.connect(
            lambda: self._voltar_para_inicial()
        )

        linha = QHBoxLayout()
        linha.setSpacing(12)
        linha.addWidget(botao)
        linha.addWidget(self._titulo(titulo))
        linha.addStretch()

        return linha, botao

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

        self._aviso_fase = self._texto_apoio(
            "A escolha já é gravada em config.json, mas a chamada "
            "ainda não a usa: a integração com o início da chamada "
            "é a próxima etapa."
        )

        layout.addWidget(self._aviso_fase)

        return pagina

    def _ao_trocar_perfil_selecionado(self):
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

        if perfis.perfil_ativo() != slug:
            try:
                perfis.definir_perfil_ativo(slug)

            except FileNotFoundError:
                pass

    def slug_selecionado(self):
        dados = self._select_perfis.currentData()

        return dados if dados else None

    def recarregar_perfis(self, slug_para_selecionar=None):
        alvo = (
            slug_para_selecionar
            or self.slug_selecionado()
            or perfis.perfil_ativo()
        )

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

        self._aviso_inventadas = self._texto_apoio("")
        self._aviso_inventadas.setStyleSheet(
            f"color: {ACCENT_BRILHO}; font-size: 10px;"
        )
        layout.addWidget(self._aviso_inventadas)

        self._aviso_cerebro_confirmacao = self._texto_apoio("")
        self._aviso_cerebro_confirmacao.setStyleSheet(
            f"color: {ACCENT_BRILHO}; font-size: 10px;"
        )
        layout.addWidget(self._aviso_cerebro_confirmacao)

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
            self._aviso_inventadas.setText(
                "A IA citou ferramenta que não existe no projeto e "
                f"ela foi descartada: {', '.join(inventadas)}"
            )

        else:
            self._aviso_inventadas.setText("")

        self._reler_cerebro_ativo()

        resumo_cerebro = self._resumo_indisponiveis(
            sugestao["ferramentas"]
        )

        self._aviso_cerebro_confirmacao.setText(
            f"Cérebro atual: {self._rotulo_cerebro}."
            + (f"\n{resumo_cerebro}" if resumo_cerebro else "")
        )

        comuns, sensiveis = perfis.separar(sugestao["ferramentas"])

        self._rotulo_comuns.setText(
            f"FERRAMENTAS COMUNS ({len(comuns)}) — ENTRAM DIRETO"
        )

        self._lista_comuns.clear()

        for nome in comuns:
            linha = QListWidgetItem(
                f"{nome}  —  {self._sufixo_cerebro(nome)}"
                f"{perfis.resumo_de(nome)}"
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
                f"{nome}  —  {self._sufixo_cerebro(nome)}"
                f"{perfis.motivo_de(nome)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, nome)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )

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

        self._rotulo_ferramentas = self._rotulo_secao(
            "FERRAMENTAS DO PERFIL"
        )
        layout.addWidget(self._rotulo_ferramentas)

        self._aviso_ferramentas = self._texto_apoio("")
        layout.addWidget(self._aviso_ferramentas)

        self._aviso_cerebro = self._texto_apoio("")
        self._aviso_cerebro.setStyleSheet(
            f"color: {ACCENT_BRILHO}; font-size: 10px;"
        )
        layout.addWidget(self._aviso_cerebro)

        self._lista_ferramentas = QListWidget()
        self._lista_ferramentas.setStyleSheet(_ESTILO_LISTA)
        self._lista_ferramentas.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self._lista_ferramentas.itemChanged.connect(
            self._ao_marcar_ferramenta
        )

        self._lista_ferramentas.setMinimumHeight(230)

        self._lista_ferramentas.setTextElideMode(
            Qt.TextElideMode.ElideRight
        )
        self._lista_ferramentas.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        layout.addWidget(self._lista_ferramentas, stretch=3)

        layout.addSpacing(10)

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
        self._reler_cerebro_ativo()

        marcadas = set(perfis.ferramentas_efetivas(perfil))

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

    def _reler_cerebro_ativo(self):
        usar_openai = perfis.cerebro_atual_usa_openai()

        self._nomes_do_cerebro = perfis.nomes_do_cerebro(usar_openai)
        self._rotulo_cerebro = perfis.nome_do_cerebro(usar_openai)

    def _fora_do_cerebro(self, nome):
        return bool(self._nomes_do_cerebro) and (
            nome not in self._nomes_do_cerebro
        )

    def _sufixo_cerebro(self, nome):
        if self._fora_do_cerebro(nome):
            return f"[não existe no {self._rotulo_cerebro}] "

        return ""

    def _resumo_indisponiveis(self, nomes):
        fora = [nome for nome in nomes if self._fora_do_cerebro(nome)]

        if not fora:
            return ""

        return (
            f"⚠ {len(fora)} destas não existem no {self._rotulo_cerebro} "
            "e serão ignoradas na chamada: " + ", ".join(fora)
        )

    def _item_ferramenta(self, entrada, marcadas):
        nome = entrada["nome"]
        obrigatoria = nome in perfis.FERRAMENTAS_SEMPRE_ATIVAS

        item = QListWidgetItem(
            f"{nome}  —  {self._sufixo_cerebro(nome)}"
            f"{entrada['resumo']}"
        )
        item.setData(Qt.ItemDataRole.UserRole, nome)

        if obrigatoria:
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

        if perfis.e_sensivel(nome):
            item.setForeground(QColor(ACCENT_BRILHO))
            item.setToolTip(f"Sensível — {perfis.motivo_de(nome)}")

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

        resumo = self._resumo_indisponiveis(marcadas)

        self._aviso_cerebro.setText(
            f"Cérebro atual: {self._rotulo_cerebro}."
            + (f"\n{resumo}" if resumo else "")
        )

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

        self._voltar_para_inicial(perguntar=False)
        self.recarregar_perfis(slug_para_selecionar=salvo)

    def _apagar_perfil_atual(self):
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

        self._voltar_para_inicial(perguntar=False)
        self.recarregar_perfis()

    def _voltar_para_inicial(self, perguntar=True):
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
    terminou = Signal(bool, object)

    def __init__(self, descricao):
        super().__init__()

        self._descricao = descricao

    def run(self):
        try:
            sucesso, resultado = perfis.gerar_sugestao(self._descricao)

        except Exception as erro:
            sucesso, resultado = False, f"Erro inesperado: {erro}"

        self.terminou.emit(sucesso, resultado)
