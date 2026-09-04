# Input pra editar o nome de identidade do assistente (NOME_JARVIS,
# padrão "ALFRED") direto na tela principal — antes só dava pra trocar
# entrando na tela de configurações. Esse nome é o que aparece em
# TUDO: instrução de sistema (jarvis/nucleo/prompts/, "Seu nome é
# <nome>." e as demais menções), o status falado/exibido ("<nome>
# conectado. Pode falar." — jarvis/gemini/cliente_live.py e
# jarvis/openai_realtime/cliente_realtime.py), e a própria tela
# principal (título da janela, rótulo lateral, texto desenhado no
# centro da esfera — ver jarvis/ui/janela_principal.py::
# _aplicar_nome_novo e jarvis/ui/visualizador_alfred.py::definir_nome).
#
# Lê/escreve o .env com a MESMA técnica de
# jarvis/pacotes/configuracoes/env_io.py (dotenv_values só lê, set_key
# atualiza uma variável sem tocar no resto do arquivo) — copiada, não
# importada, mesmo princípio já usado em jarvis/ui/painel_provedor.py
# (ver o comentário no topo daquele arquivo pro porquê).
from dotenv import dotenv_values, set_key

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from jarvis.caminhos import CAMINHO_ENV

NOME_PADRAO = "ALFRED"

# Mesmo limite de caracteres usado como "campo curto" em outros
# lugares do projeto (ex: jarvis/pacotes/criar_arquivo — nome de
# arquivo) — o nome entra em frases inteiras da instrução de sistema
# ("Seu nome é <nome>."), então precisa ficar curto por natureza.
LIMITE_CARACTERES = 30


def _ler_nome_atual():
    if not CAMINHO_ENV.exists():
        return NOME_PADRAO

    valores = dotenv_values(CAMINHO_ENV)

    return (valores.get("NOME_JARVIS") or NOME_PADRAO).strip() or NOME_PADRAO


def _salvar_nome(nome):
    CAMINHO_ENV.touch(exist_ok=True)

    set_key(
        str(CAMINHO_ENV),
        "NOME_JARVIS",
        nome,
        quote_mode="never",
    )


class PainelNome(QWidget):

    def __init__(self, ao_alterar=None, parent=None):
        super().__init__(parent)

        # Chamado com o nome novo (já salvo no .env nesse momento)
        # toda vez que o usuário confirma uma edição — quem instancia
        # este painel (jarvis/ui/janela_principal.py) usa isso pra
        # atualizar título/rótulo/esfera na hora.
        self._ao_alterar = ao_alterar

        self._ultimo_valor_salvo = _ler_nome_atual()

        self._montar()

    def _montar(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        rotulo = QLabel("Nome")
        rotulo.setObjectName("statusTitulo")

        self.campo = QLineEdit(self._ultimo_valor_salvo)
        self.campo.setPlaceholderText(NOME_PADRAO)
        self.campo.setMaxLength(LIMITE_CARACTERES)

        layout.addWidget(rotulo)
        layout.addWidget(self.campo, 1)

        # editingFinished dispara tanto no Enter quanto ao tirar o
        # foco do campo (clicar em outro lugar) — nunca a cada tecla
        # digitada, o que escreveria no .env a cada letra.
        self.campo.editingFinished.connect(self._ao_terminar_edicao)

    def _ao_terminar_edicao(self):
        nome = self.campo.text().strip() or NOME_PADRAO

        self.campo.setText(nome)

        # Sem esta checagem, confirmar duas vezes o mesmo valor (Enter
        # e depois tirar o foco, ou salvar sem ter mudado nada)
        # reescreveria o .env à toa — inofensivo, mas evitável.
        if nome == self._ultimo_valor_salvo:
            return

        try:
            _salvar_nome(nome)

        except OSError as erro:
            print(
                f"[NOME] Não consegui salvar no .env: {erro}"
            )

            return

        self._ultimo_valor_salvo = nome

        print(
            f"[NOME] Nome de identidade: {nome} "
            "(já atualizado na tela e válido já na próxima chamada)."
        )

        if self._ao_alterar:
            self._ao_alterar(nome)
