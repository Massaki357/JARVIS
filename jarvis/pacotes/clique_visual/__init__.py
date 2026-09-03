"""
Clique em um elemento da tela descrito por voz.

Trazido do JARVIS COMPLETO, onde era uma tool nativa do
gemini/live_client.py ligando vision/click_locator.py a
actions/mouse_actions.mover_e_clicar. Aqui virou um pacote isolado no
contrato padrão do projeto — ver docs/INTEGRATION.md.

Fluxo de uma chamada:

1. localizador_clique.localizar_elemento_na_tela(alvo) recusa alvo
   vazio, BLOQUEIA por palavra-chave qualquer alvo que pareça ação
   sensível/destrutiva (excluir, formatar, comprar, pagar, instalar,
   "executar como administrador"...) ANTES mesmo de capturar a tela,
   captura o monitor principal, pergunta a um modelo Gemini visual
   separado onde está o elemento e recusa o resultado se o modelo não
   encontrou ou se a confiança ficou abaixo de CONFIANCA_MINIMA.
2. Só com um alvo aprovado, controle_mouse.acoes.mover_e_clicar move
   o cursor e clica.

Duas observações de integração:

- Este é o único pacote que importa de outro pacote
  (controle_mouse.acoes.mover_e_clicar). É deliberado e numa direção
  só: as duas metades vieram do mesmo módulo de mouse do curso, e uma
  segunda cópia do código de ctypes que move o cursor envelheceria
  fora de sincronia com a primeira. mover_e_clicar continua sem ser
  exposta como tool em lugar nenhum — ver o docstring de
  controle_mouse.
- despachar() CAPTURA A TELA por dentro (dentro do localizador). Por
  isso o cliente Live segura self._mutex_funcao_visual() em volta do
  despacho de clicar_elemento_visual, igual já faz com
  identificar_planta/consultar_segunda_opiniao_visual — ver
  jarvis/gemini/cliente_live.py e docs/INTEGRATION.md.
"""

# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from jarvis.servicos.visao.localizador_clique import (
    localizar_elemento_na_tela,
)

from jarvis.pacotes.controle_mouse import acoes as acoes_mouse

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="clicar_elemento_visual",
        description=(
            "Captura a tela atual, localiza visualmente um elemento "
            "descrito pelo usuário, move o mouse até o centro do alvo "
            "e executa um clique esquerdo. Use somente quando o usuário "
            "pedir claramente para clicar em algo identificado por texto, "
            "posição, cor, ícone ou contexto, como 'clique em Continuar', "
            "'clique no primeiro resultado' ou 'clique no botão vermelho'. "
            "Não use para exclusões, compras, pagamentos, instalações, "
            "ações administrativas ou confirmações sensíveis. "
            "Execute uma única vez por solicitação e permaneça em silêncio."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "alvo": types.Schema(
                    type="STRING",
                    description=(
                        "Descrição objetiva do elemento visível "
                        "que deve receber o clique."
                    ),
                )
            },
            required=["alvo"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao != "clicar_elemento_visual":
        return None

    alvo = argumentos.get("alvo", "")

    # Nunca levanta exceção pra fora: a mensagem de falha do
    # localizador já é um texto pronto pro ALFRED falar, e uma falha
    # inesperada aqui viraria erro de tool no meio da chamada.
    try:
        localizacao = localizar_elemento_na_tela(alvo)

    except Exception as erro:
        return (
            "Não consegui analisar a tela para localizar esse "
            f"elemento ({type(erro).__name__}). Nenhum clique foi "
            "executado."
        )

    if not localizacao.get("sucesso"):
        return localizacao.get(
            "mensagem",
            "Não consegui localizar esse elemento. Nenhum clique "
            "foi executado.",
        )

    resultado_clique = acoes_mouse.mover_e_clicar(
        localizacao["x"],
        localizacao["y"],
    )

    return (
        f"{resultado_clique} Elemento: "
        f"{localizacao.get('descricao', alvo)}."
    )
