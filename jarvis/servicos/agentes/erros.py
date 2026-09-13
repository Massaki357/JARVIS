"""
Classificação das falhas que os provedores de LLM devolvem, num
vocabulário único — independente de qual SDK levantou a exceção.

POR QUE ISTO EXISTE
===================

Antes do LangChain, cada chamada era um requests.post() e o código
lia o status HTTP direto: 429 era limite, 401 era chave errada, e o
cabeçalho retry-after dizia quanto esperar. Com o LangChain, quem
fala com a rede é o SDK de cada provedor (groq, openai,
google-genai, httpx da Mistral), e a falha chega como EXCEÇÃO — de
um tipo diferente por provedor.

O roteamento hierárquico (jarvis/roteamento_hierarquico/roteador.py)
depende dessa distinção para decidir se repete ou desiste, e o
comentário gigante de lá explica por quê: repetir um 401 é gastar o
tempo do usuário para receber o mesmo erro, mas repetir um 429 (a
janela reabre em ~1s) ou o 400 de "o modelo chamou uma ferramenta
que ninguém declarou" (não determinístico) resolve de verdade.

Essa inteligência NÃO podia se perder na migração. Então ela mudou
de lugar, não de existência: em vez de ler o status HTTP, este
módulo olha o tipo e o texto da exceção. Os SDKs da Groq e da OpenAI
ainda carregam a resposta HTTP original em erro.response, então o
retry-after continua sendo lido da fonte — nunca adivinhado.
"""

import re

# Os quatro veredictos possíveis. Nomes curtos de propósito: quem
# consome compara com uma constante, nunca com um texto solto.
LIMITE = "limite"
TEMPO = "tempo"
AUTENTICACAO = "autenticacao"
FERRAMENTA_INDEVIDA = "ferramenta_indevida"
DESCONHECIDO = "desconhecido"

# "Please try again in 975ms" / "try again in 1.5s" — a Groq manda a
# espera exata dentro da mensagem, além do cabeçalho. Quando o
# cabeçalho não vem (acontece), este é o segundo melhor palpite, e
# ainda é o servidor falando, não nós chutando.
_PADRAO_ESPERA_NA_MENSAGEM = re.compile(
    r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s)\b",
    re.IGNORECASE,
)


def cabecalho(erro, nome):
    """
    Um cabeçalho HTTP da resposta que gerou a exceção, quando o SDK a
    preserva (a Groq e a OpenAI guardam em .response; o
    langchain-mistralai levanta httpx.HTTPStatusError, que também
    tem). Devolve None quando não dá para saber.

    Existe porque um cabeçalho às vezes diz algo que a mensagem não
    diz. O caso concreto deste projeto: a Mistral responde 429 tanto
    para "rápido demais" quanto para "acabou a cota", e só o
    x-ratelimit-limit-req-minute (que vem ZERADO no segundo caso)
    separa os dois. Chamar cota esgotada de "limite por minuto"
    mandaria o usuário esperar por algo que não vai reabrir sozinho.
    """
    resposta = getattr(erro, "response", None)
    cabecalhos = getattr(resposta, "headers", None)

    if cabecalhos is None:
        return None

    try:
        return cabecalhos.get(nome)

    except Exception:
        return None


def _codigo_http(erro):
    """
    Status HTTP da exceção, quando o SDK o expõe. Os SDKs da Groq e
    da OpenAI guardam a httpx.Response inteira em .response e o
    número em .status_code; o google-genai usa .code. Nenhum deles é
    obrigatório — devolve None quando não dá para saber.
    """
    for atributo in ("status_code", "code"):
        valor = getattr(erro, atributo, None)

        if isinstance(valor, int):
            return valor

    resposta = getattr(erro, "response", None)
    valor = getattr(resposta, "status_code", None)

    return valor if isinstance(valor, int) else None


def e_chamada_de_ferramenta_indevida(texto):
    """
    Reconhece o 400 em que o MODELO saiu do combinado: emitiu uma
    chamada de ferramenta numa requisição que não declarou ferramenta
    nenhuma ("Tool choice is none, but model called a tool").

    Mesma regra de antes da migração, mesma razão: é a ÚNICA exceção
    à regra de não repetir 4xx, porque a resposta não é função só da
    requisição — medido de 1 a 3 falhas em cada 6 chamadas idênticas.
    """
    texto = (texto or "").lower()

    return "tool" in texto and (
        "tool choice is none" in texto or "called a tool" in texto
    )


def classificar(erro):
    """
    Devolve uma das constantes acima para a exceção dada. Nunca
    levanta — uma falha ao classificar a falha viraria um bug muito
    pior que o original.
    """
    texto = str(erro or "")
    minusculo = texto.lower()
    nome_tipo = type(erro).__name__.lower()

    if e_chamada_de_ferramenta_indevida(texto):
        return FERRAMENTA_INDEVIDA

    codigo = _codigo_http(erro)

    if codigo == 429 or "ratelimit" in nome_tipo:
        return LIMITE

    if codigo in (401, 403) or "authentication" in nome_tipo:
        return AUTENTICACAO

    if "timeout" in nome_tipo or "timed out" in minusculo:
        return TEMPO

    # Último recurso: o texto. Alguns SDKs embrulham a falha numa
    # exceção genérica e só o texto sobrou como sinal.
    if "rate limit" in minusculo or "quota" in minusculo:
        return LIMITE

    if "api key" in minusculo or "unauthorized" in minusculo:
        return AUTENTICACAO

    return DESCONHECIDO


def espera_sugerida(erro, tentativa, base, maximo):
    """
    Quanto esperar antes de repetir, em segundos.

    Prioridade: o cabeçalho retry-after (ninguém adivinha melhor que
    o próprio servidor quando a janela reabre), depois a espera dita
    dentro da mensagem, e só então o backoff exponencial local.

    SEMPRE limitado por `maximo`, porque os dois primeiros vêm de
    fora: um valor absurdo travaria o turno de voz por muito mais
    tempo do que vale a pena esperar falando.
    """
    resposta = getattr(erro, "response", None)
    cabecalhos = getattr(resposta, "headers", None)

    if cabecalhos is not None:
        try:
            cabecalho = cabecalhos.get("retry-after")

        except Exception:
            cabecalho = None

        if cabecalho:
            try:
                return min(float(cabecalho), maximo)

            except (TypeError, ValueError):
                pass

    encontrado = _PADRAO_ESPERA_NA_MENSAGEM.search(str(erro or ""))

    if encontrado:
        try:
            valor = float(encontrado.group(1))

            if encontrado.group(2).lower() == "ms":
                valor = valor / 1000.0

            return min(valor, maximo)

        except (TypeError, ValueError):
            pass

    return min(base * (2 ** tentativa), maximo)


def descrever(erro):
    """
    Texto curto e legível da falha, para entrar numa mensagem
    devolvida ao cérebro. Inclui o tipo porque, com vários SDKs
    diferentes por trás, só a mensagem costuma não dizer quem falhou.
    """
    texto = str(erro or "").strip()

    if not texto:
        return type(erro).__name__

    return f"{type(erro).__name__}: {texto[:200]}"
