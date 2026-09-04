# Criação de um perfil a partir de uma descrição em texto livre: monta
# o pedido, chama o modelo, e valida o que voltou.
#
# Este módulo NÃO grava nada e NÃO decide o que entra no perfil. Ele
# devolve uma sugestão já validada; quem separa o que entra direto do
# que precisa da aprovação do usuário é a etapa de confirmação da tela
# (usando jarvis/nucleo/perfis/sensiveis.py), e quem grava é
# armazenamento.criar_perfil.
#
# QUAL MODELO É CHAMADO
# =====================
#
# O cérebro que o usuário escolheu em PROVEDOR_IA (.env) — Gemini ou
# OpenAI. Isso é requisito da funcionalidade, não detalhe: a descrição
# do perfil vai para a mesma IA que conduz as chamadas de voz.
#
# A chamada passa por jarvis/pacotes/delegacao_ia (rota
# delegar_para_cerebro_configurado), e não por um cliente próprio
# daqui, por dois motivos que se resolvem juntos:
#
# 1. delegacao_ia é onde este projeto centraliza "mandar um pedido de
#    texto pontual para outra LLM". Um cliente HTTP novo aqui seria
#    uma segunda implementação da mesma coisa.
# 2. O CLAUDE.md permite exatamente DUAS portas de entrada para a
#    OpenAI, e delegacao_ia é uma delas. Chamar a OpenAI direto daqui
#    quando PROVEDOR_IA=openai abriria uma terceira, não sancionada.
#
# NÃO existe fallback para outro provedor, de propósito: se o cérebro
# configurado não responde, a tela diz isso e o usuário tenta de novo.
# Cair calado em outra IA entregaria um perfil escrito por quem o
# usuário não escolheu.
#
import json
import re
import time

from jarvis.nucleo import prompts
from jarvis.nucleo.config import obter_nome_jarvis
from jarvis.pacotes import delegacao_ia

from . import armazenamento, catalogo_ferramentas

# QUAL modelo cada cérebro usa é decisão de delegacao_ia/config.py
# (DELEGACAO_MODELO_GEMINI / DELEGACAO_MODELO_OPENAI) — deliberadamente
# NÃO tem uma constante de modelo aqui, senão o projeto teria dois
# lugares dizendo qual modelo falar com o mesmo provedor.
#
# A retentativa fica aqui porque é política desta tela, não do
# provedor: 503 (modelo sobrecarregado) e 429 (limite) aparecem de
# verdade, e sem retentativa um pico de demanda vira "não consegui
# criar o perfil" na cara do usuário.
TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS_SEGUNDOS = 5

# Teto do texto livre que o usuário digita. Não é uma trava de
# segurança, é sanidade: a descrição de um perfil são algumas frases,
# e um texto gigante colado por engano só gastaria token.
LIMITE_CARACTERES_DESCRICAO = 4000

# Teto do nome de exibição que o modelo devolve, para não estourar o
# select da tela. Truncar é melhor que recusar a geração inteira por
# causa de um nome comprido.
LIMITE_CARACTERES_NOME = 40


def montar_catalogo_para_prompt():
    """
    Texto do catálogo que vai dentro do pedido: uma linha por
    ferramenta, agrupada por categoria.

    Sai de perfis.catalogo_completo(), que por sua vez deriva os nomes
    de PACOTES_REGISTRADOS e reaproveita os resumos de uma linha de
    jarvis/roteamento_hierarquico/catalogo.py. Não existe uma segunda
    lista de "quais ferramentas existem" escrita para este prompt.
    """
    linhas = []
    categoria_anterior = None

    for item in catalogo_ferramentas.catalogo_completo():
        if item["rotulo_categoria"] != categoria_anterior:
            categoria_anterior = item["rotulo_categoria"]
            linhas.append(f"\n## {categoria_anterior}")

        linhas.append(f"- {item['nome']}: {item['resumo']}")

    return "\n".join(linhas).strip()


def montar_pedido(descricao):
    """
    O prompt exato enviado ao modelo. Separado da chamada de rede de
    propósito: dá para inspecionar e testar o texto sem gastar uma
    requisição.
    """
    return prompts.CRIACAO_PERFIL.format(
        nome_assistente=obter_nome_jarvis(),
        descricao=str(descricao or "").strip()[
            :LIMITE_CARACTERES_DESCRICAO
        ],
        catalogo=montar_catalogo_para_prompt(),
    )


# O formato da resposta é pedido em duas camadas. A primeira é o modo
# JSON nativo do provedor (json_esperado=True lá embaixo), que faz o
# próprio serviço garantir JSON válido. A segunda é
# interpretar_resposta(), que valida tudo de novo em código.
#
# A segunda não é redundante: modo JSON garante SINTAXE, nunca
# conteúdo. Nenhum provedor promete que os nomes de ferramenta que
# vierem lá dentro existem neste projeto — e é exatamente isso que
# precisa ser conferido.


def _extrair_json(texto):
    """
    Devolve o dict do JSON da resposta.

    Tenta o texto inteiro primeiro; se não for JSON puro, procura o
    conteúdo de uma cerca ```json e, por último, o maior trecho entre
    a primeira "{" e a última "}". Levanta ValueError se nada servir.
    """
    texto = (texto or "").strip()

    tentativas = [texto]

    cerca = re.search(
        r"```(?:json)?\s*(.+?)\s*```", texto, re.DOTALL
    )

    if cerca:
        tentativas.append(cerca.group(1))

    if "{" in texto and "}" in texto:
        tentativas.append(
            texto[texto.index("{"): texto.rindex("}") + 1]
        )

    for candidato in tentativas:
        try:
            dados = json.loads(candidato)

        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(dados, dict):
            return dados

    raise ValueError(
        "O modelo não devolveu um objeto JSON reconhecível."
    )


def interpretar_resposta(texto):
    """
    Valida a resposta do modelo e devolve
    {"nome", "ferramentas", "prompt_sistema", "inexistentes"}.

    Regras, todas em código e nenhuma confiada ao prompt:

    - Nome de ferramenta que não existe no projeto é ERRO. Ele não é
      descartado em silêncio: volta em "inexistentes" para a tela
      mostrar o que foi ignorado, porque um modelo inventando nome é
      sinal de que o resto da resposta também merece desconfiança.
    - Repetição é removida, preservando a ordem.
    - Prompt de sistema vazio é ERRO: um perfil sem prompt não
      configura nada.

    Levanta ValueError em qualquer caso irrecuperável.
    """
    dados = _extrair_json(texto)

    nome = str(dados.get("nome") or "").strip()[
        :LIMITE_CARACTERES_NOME
    ]

    prompt_sistema = str(dados.get("prompt_sistema") or "").strip()

    if not prompt_sistema:
        raise ValueError(
            "O modelo não devolveu o prompt de sistema do perfil."
        )

    brutas = dados.get("ferramentas") or []

    if not isinstance(brutas, list):
        raise ValueError(
            "O campo \"ferramentas\" da resposta não é uma lista."
        )

    disponiveis = catalogo_ferramentas.nomes_disponiveis()

    escolhidas = []
    inexistentes = []

    for bruta in brutas:
        candidata = str(bruta or "").strip()

        if not candidata:
            continue

        if candidata not in disponiveis:
            if candidata not in inexistentes:
                inexistentes.append(candidata)

            continue

        if candidata not in escolhidas:
            escolhidas.append(candidata)

    return {
        "nome": nome or "Perfil sem nome",
        "ferramentas": escolhidas,
        "prompt_sistema": prompt_sistema,
        "inexistentes": inexistentes,
    }


def _chamar_modelo(pedido):
    """
    Manda o pedido ao cérebro configurado e devolve
    (sucesso, texto_ou_erro). Nunca levanta.

    Retenta com espera crescente: a falha típica aqui é temporária
    (503 de modelo sobrecarregado, 429 de limite), e desistir na
    primeira jogaria fora uma geração que ia funcionar na segunda.
    """
    ultimo_erro = ""

    for tentativa in range(TENTATIVAS):
        if tentativa:
            time.sleep(ESPERA_ENTRE_TENTATIVAS_SEGUNDOS * tentativa)

        sucesso, resultado = (
            delegacao_ia.roteador.delegar_para_cerebro_configurado(
                pedido,
                json_esperado=True,
                timeout=delegacao_ia.config.TIMEOUT_LONGO_SEGUNDOS,
            )
        )

        if sucesso:
            return True, resultado

        ultimo_erro = resultado

        print(
            f"[perfis] Tentativa {tentativa + 1} de {TENTATIVAS} "
            f"falhou: {str(resultado)[:150]}"
        )

    return False, ultimo_erro


def gerar_sugestao(descricao):
    """
    Ponta a ponta: descrição em texto livre -> sugestão validada.

    Devolve (sucesso, resultado). Em caso de sucesso, resultado é o
    dict de interpretar_resposta acrescido de "slug_sugerido". Em caso
    de falha, resultado é uma mensagem em português pronta para ser
    mostrada — nunca uma exceção, porque quem chama é um slot da
    interface.

    BLOQUEIA (é uma requisição HTTP): a tela precisa chamar isto fora
    da thread da GUI, ou a janela congela enquanto o modelo pensa.
    """
    descricao = str(descricao or "").strip()

    if not descricao:
        return False, "Descreva o perfil antes de gerar."

    sucesso, texto = _chamar_modelo(montar_pedido(descricao))

    if not sucesso:
        return False, texto

    try:
        sugestao = interpretar_resposta(texto)

    except ValueError as erro:
        return False, str(erro)

    sugestao["slug_sugerido"] = armazenamento.slug_disponivel(
        sugestao["nome"]
    )
    sugestao["descricao"] = descricao

    return True, sugestao
