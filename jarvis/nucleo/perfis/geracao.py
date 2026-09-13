import json
import re
import time

from jarvis.nucleo import prompts
from jarvis.nucleo.config import obter_nome_jarvis
from jarvis.pacotes import delegacao_ia

from . import armazenamento, catalogo_ferramentas

TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS_SEGUNDOS = 5

LIMITE_CARACTERES_DESCRICAO = 4000

LIMITE_CARACTERES_NOME = 40


def montar_catalogo_para_prompt():
    linhas = []
    categoria_anterior = None

    for item in catalogo_ferramentas.catalogo_completo():
        if item["rotulo_categoria"] != categoria_anterior:
            categoria_anterior = item["rotulo_categoria"]
            linhas.append(f"\n## {categoria_anterior}")

        linhas.append(f"- {item['nome']}: {item['resumo']}")

    return "\n".join(linhas).strip()


def montar_pedido(descricao):
    return prompts.CRIACAO_PERFIL.format(
        nome_assistente=obter_nome_jarvis(),
        descricao=str(descricao or "").strip()[
            :LIMITE_CARACTERES_DESCRICAO
        ],
        catalogo=montar_catalogo_para_prompt(),
    )


def _extrair_json(texto):
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
