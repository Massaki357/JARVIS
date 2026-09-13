import re

LIMITE = "limite"
TEMPO = "tempo"
AUTENTICACAO = "autenticacao"
FERRAMENTA_INDEVIDA = "ferramenta_indevida"
DESCONHECIDO = "desconhecido"

_PADRAO_ESPERA_NA_MENSAGEM = re.compile(
    r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s)\b",
    re.IGNORECASE,
)


def cabecalho(erro, nome):
    resposta = getattr(erro, "response", None)
    cabecalhos = getattr(resposta, "headers", None)

    if cabecalhos is None:
        return None

    try:
        return cabecalhos.get(nome)

    except Exception:
        return None


def _codigo_http(erro):
    for atributo in ("status_code", "code"):
        valor = getattr(erro, atributo, None)

        if isinstance(valor, int):
            return valor

    resposta = getattr(erro, "response", None)
    valor = getattr(resposta, "status_code", None)

    return valor if isinstance(valor, int) else None


# Único 4xx que vale repetir: a resposta varia entre chamadas idênticas.
def e_chamada_de_ferramenta_indevida(texto):
    texto = (texto or "").lower()

    return "tool" in texto and (
        "tool choice is none" in texto or "called a tool" in texto
    )


def classificar(erro):
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

    if "rate limit" in minusculo or "quota" in minusculo:
        return LIMITE

    if "api key" in minusculo or "unauthorized" in minusculo:
        return AUTENTICACAO

    return DESCONHECIDO


def espera_sugerida(erro, tentativa, base, maximo):
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
    texto = str(erro or "").strip()

    if not texto:
        return type(erro).__name__

    return f"{type(erro).__name__}: {texto[:200]}"
