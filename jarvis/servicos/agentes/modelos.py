"""
Fábrica de modelos de chat do LangChain — um provedor por nome, com
os mesmos nomes que o resto do projeto já usa ("gemini", "openai",
"groq", "cerebras", "mistral").

POR QUE UMA FÁBRICA, E NÃO CADA PACOTE CONSTRUINDO O SEU
========================================================

Antes desta camada, cada lugar que falava com uma LLM montava o
cliente do zero: quatro requests.post() com o cabeçalho Authorization
escrito à mão, três genai.Client() com HttpOptions em MILISSEGUNDOS
(enquanto os outros contavam segundos), e cada um lembrando — ou
esquecendo — de pôr timeout. Mais de uma trava silenciosa deste
projeto nasceu exatamente de um cliente sem timeout.

Aqui o timeout é OBRIGATÓRIO: não existe caminho que construa um
modelo sem um. É a única regra desta camada que não tem exceção.

CADA MODELO É CACHEADO por combinação de (provedor, modelo,
temperatura, timeout, chave). Construir um cliente HTTP por chamada
era desperdício puro — o cliente é sem estado, a conversa toda vai
no invoke(). A chave de API entra no identificador do cache só para
não misturar dois clientes de contas diferentes; ela NUNCA aparece em
mensagem de erro, log ou repr (regra do CLAUDE.md).

POR QUE A CEREBRAS USA O ChatOpenAI
===================================

Existe um langchain-cerebras, mas da versão 0.7.0 em diante ele exige
Python <3.13, e a venv deste projeto é 3.13.4 — só a 0.6.0 instalaria,
e ela arrasta um langchain-openai <1.0 que REBAIXARIA o pacote openai
de 3.x para 2.x. Isso quebraria o cérebro de voz da OpenAI Realtime
(jarvis/cerebro/openai_realtime/), que é código em produção.

A Cerebras expõe a API no formato da OpenAI (foi por isso que ela
cabia no _chamar_completions genérico antes desta migração), então
ChatOpenAI com base_url apontando para api.cerebras.ai é o MESMO
caminho de rede de antes, só que dentro do LangChain. Nada de
padronização se perde; o que se evita é rebaixar um SDK em uso.
"""

# Timeout padrão, em SEGUNDOS. Quem chama quase sempre passa o seu
# (cada pacote tem o próprio, por motivos próprios — 8s numa resposta
# falada, 60s numa tela que mostra "consultando o modelo..."). Este
# valor só existe para que "sem timeout" nunca seja uma possibilidade.
TIMEOUT_PADRAO_SEGUNDOS = 30

# Provedores que esta camada sabe construir. O valor é o
# model_provider do init_chat_model mais o que aquele provedor exige
# de diferente:
#
#   parametro_chave  — o google-genai chama de google_api_key, os
#                      outros de api_key;
#   extras           — argumentos fixos de construção (a base_url da
#                      Cerebras);
#   timeout_minimo   — o piso que a API aceita (ver TIMEOUTS abaixo);
#   binds            — argumentos amarrados a cada invocação (ver
#                      argumentos_de_invocacao).
_PROVEDORES = {
    "gemini": {
        "model_provider": "google_genai",
        "parametro_chave": "google_api_key",
        "extras": {},
        # PISO REAL DA API, medido ao vivo, não estimado: com timeout
        # de 8s a chamada volta 400 INVALID_ARGUMENT com "Manually set
        # deadline 8s is too short. Minimum allowed deadline is 10s."
        # O 8s de jarvis/pacotes/delegacao_ia/config.py é legítimo para
        # Groq/Cerebras/OpenAI e não devia mudar por causa do Gemini —
        # então o piso vive aqui, junto do provedor que o impõe.
        # Subir o pedido até o mínimo é estritamente melhor do que uma
        # recusa garantida.
        "timeout_minimo": 10,
        # Sem isto o SDK imprime um aviso sobre "automatic function
        # calling" a cada chamada — ruído puro no painel de console do
        # app, que duplica o stdout. Este projeto nunca usa AFC: quando
        # há ferramenta, quem decide o que executar é o despachante dos
        # pacotes, nunca o SDK chamando função Python sozinho.
        "binds": {"automatic_function_calling": {"disable": True}},
        "pacote_pip": "langchain-google-genai",
    },
    "openai": {
        "model_provider": "openai",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-openai",
    },
    "groq": {
        "model_provider": "groq",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-groq",
    },
    "cerebras": {
        "model_provider": "openai",
        "parametro_chave": "api_key",
        "extras": {"base_url": "https://api.cerebras.ai/v1"},
        "pacote_pip": "langchain-openai",
    },
    "mistral": {
        "model_provider": "mistralai",
        "parametro_chave": "api_key",
        "extras": {},
        "pacote_pip": "langchain-mistralai",
    },
}

PROVEDORES_SUPORTADOS = tuple(_PROVEDORES.keys())

_cache = {}


class ProvedorDesconhecido(ValueError):
    """O nome do provedor não está em PROVEDORES_SUPORTADOS."""


class ProvedorIndisponivel(RuntimeError):
    """
    O provedor existe, mas o pacote de integração do LangChain dele
    não está instalado nesta máquina.

    É um erro separado de propósito: a mensagem diz o comando de pip
    que resolve, em vez de deixar um ImportError cru subir por uma
    chamada de voz.
    """


def _identificador_cache(provedor, modelo, temperatura, timeout, api_key):
    # A chave entra como hash, não como texto: ela nunca precisa ser
    # legível para separar um cliente do outro, e assim não existe
    # nenhum lugar em memória onde ela apareça por engano.
    return (
        provedor,
        modelo,
        temperatura,
        timeout,
        hash(api_key or ""),
    )


def criar_modelo(
    provedor,
    modelo,
    api_key,
    temperatura=None,
    timeout=None,
):
    """
    Devolve um chat model do LangChain pronto para invoke().

    Levanta ProvedorDesconhecido, ProvedorIndisponivel ou ValueError
    (chave ausente) — quem chama normalmente é agente.executar(), que
    converte tudo isso numa RespostaAgente de falha. Chamar direto só
    faz sentido em teste.

    max_retries é fixado em 0 DE PROPÓSITO: neste projeto, quantas
    vezes repetir é política de quem chama, e cada chamador já tem a
    sua, medida contra o próprio orçamento de tokens (ver
    jarvis/roteamento_hierarquico/config.py). Deixar o LangChain
    repetir por baixo multiplicaria silenciosamente essas contas.
    """
    definicao = _PROVEDORES.get(provedor)

    if definicao is None:
        raise ProvedorDesconhecido(
            f"Provedor '{provedor}' não é suportado. "
            f"Suportados: {', '.join(PROVEDORES_SUPORTADOS)}."
        )

    if not api_key:
        raise ValueError(
            f"Nenhuma chave de API foi informada para o provedor "
            f"'{provedor}'."
        )

    timeout = timeout or TIMEOUT_PADRAO_SEGUNDOS

    # Nunca abaixo do piso do provedor: um timeout curto demais não
    # deixa a chamada rápida, deixa a chamada impossível.
    timeout = max(timeout, definicao.get("timeout_minimo", 0))

    identificador = _identificador_cache(
        provedor, modelo, temperatura, timeout, api_key
    )

    if identificador in _cache:
        return _cache[identificador]

    # Import adiado: o init_chat_model resolve o pacote do provedor na
    # hora da chamada, então importar aqui dentro faz com que só quem
    # realmente usa um provedor pague o custo de carregar o SDK dele —
    # mesmo padrão já usado nos clientes de visão deste projeto.
    from langchain.chat_models import init_chat_model

    argumentos = {
        "model_provider": definicao["model_provider"],
        definicao["parametro_chave"]: api_key,
        "timeout": timeout,
        "max_retries": 0,
        **definicao["extras"],
    }

    # Só entra quando foi pedida. Alguns modelos recusam a requisição
    # se temperature vier junto, e o padrão de cada provedor é uma
    # escolha razoável que não precisa ser sobrescrita à toa.
    if temperatura is not None:
        argumentos["temperature"] = temperatura

    try:
        construido = init_chat_model(modelo, **argumentos)

    except ImportError as erro:
        raise ProvedorIndisponivel(
            f"O pacote de integração do provedor '{provedor}' não está "
            f"instalado. Instale com: pip install "
            f"{definicao['pacote_pip']} ({erro})"
        ) from erro

    _cache[identificador] = construido

    return construido


def argumentos_de_invocacao(provedor):
    """
    O que precisa ser amarrado a CADA invocação daquele provedor,
    para quem chama não precisar saber de qual provedor se trata.

    Hoje só o Gemini tem algo aqui (desligar o automatic function
    calling do SDK, que de outro modo imprime um aviso por chamada).
    A lista mora junto da definição do provedor de propósito: é o
    lugar onde as esquisitices de cada API já estão documentadas, e
    assim jarvis/servicos/agentes/agente.py não precisa de nenhum
    "if provedor == ...".
    """
    definicao = _PROVEDORES.get(provedor) or {}

    return dict(definicao.get("binds") or {})
