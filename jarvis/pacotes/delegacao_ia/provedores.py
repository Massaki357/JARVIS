"""
Os quatro provedores de texto da delegação — Groq, Cerebras, OpenAI e
Gemini — todos pelo mesmo caminho: jarvis/servicos/agentes/.

O QUE MUDOU AQUI, E O QUE NÃO MUDOU
===================================

NÃO mudou o contrato: cada consultar_* continua devolvendo
(sucesso, texto_ou_mensagem_de_erro) e continua sem levantar exceção
nunca. O roteador deste pacote não precisou saber de nada disso.

MUDOU a implementação. Antes eram DUAS coisas diferentes no mesmo
arquivo:

  - um _chamar_completions com requests.post, que servia Groq,
    Cerebras e OpenAI porque as três expõem a API no formato da
    OpenAI (montando o cabeçalho Authorization, o corpo, e lendo
    dados["choices"][0]["message"]["content"] na mão);
  - um consultar_gemini separado, com o SDK google-genai, porque o
    Gemini NÃO expõe esse formato — com timeout em milissegundos
    enquanto o outro contava segundos, e com um
    automatic_function_calling=disable só para calar um aviso do SDK.

Agora os quatro são a mesma chamada. O LangChain cobre a diferença
de protocolo, e a diferença de timeout deixou de existir: a camada de
agentes conta em segundos para todo mundo.

A CEREBRAS continua alcançada pelo formato da OpenAI (ChatOpenAI com
base_url), pelo mesmo motivo de sempre — a API dela é compatível.
O porquê de não ser o langchain-cerebras está em
jarvis/servicos/agentes/modelos.py: a partir da 0.7.0 ele exige
Python <3.13, e esta venv é 3.13.
"""

from jarvis.servicos import agentes

from . import config


def _consultar(
    provedor,
    modelo,
    api_key,
    nome_da_chave,
    prompt,
    json_esperado=False,
    timeout=None,
):
    """
    Uma consulta de texto a um provedor. Nunca levanta exceção —
    sempre devolve (sucesso, texto_ou_mensagem_de_erro).

    nome_da_chave é só para a mensagem de erro dizer QUAL variável
    do .env está faltando; o valor dela nunca aparece em lugar
    nenhum.
    """
    if not api_key:
        return False, f"{nome_da_chave} não configurada no .env."

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor=provedor,
            modelo=modelo,
            api_key=api_key,
            texto=prompt,
            # Modo JSON nativo do provedor. Quem pede isto (a criação
            # de perfil) já valida o JSON em código de qualquer jeito
            # — isto só reduz a chance de vir texto solto em volta,
            # não substitui a validação.
            json_esperado=json_esperado,
            timeout=timeout or config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="delegacao_ia"),
    )

    if not resposta.sucesso:
        return False, f"Falha na chamada ao provedor: {resposta.erro}"

    if not resposta.texto:
        return False, "O provedor devolveu uma resposta vazia."

    return True, resposta.texto


def consultar_groq(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "groq",
        config.MODELO_GROQ,
        config.GROQ_API_KEY,
        "GROQ_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_cerebras(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "cerebras",
        config.MODELO_CEREBRAS,
        config.CEREBRAS_API_KEY,
        "CEREBRAS_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_openai(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "openai",
        config.MODELO_OPENAI,
        config.OPENAI_API_KEY,
        "OPENAI_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_gemini(prompt, json_esperado=False, timeout=None):
    """
    O Gemini pela MESMA função dos outros três.

    Antes este era o caso especial do arquivo, com um cliente e um
    tratamento de erro próprios só porque o protocolo era outro. Com
    a camada de agentes, o protocolo é problema do LangChain, e o
    Gemini vira mais uma linha igual às de cima.
    """
    return _consultar(
        "gemini",
        config.MODELO_GEMINI,
        config.GEMINI_API_KEY,
        "GEMINI_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )
