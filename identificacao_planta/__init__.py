# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver INTEGRATION.md).
from google.genai import types

from . import plantnet_client

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Diferença deste pacote em relação aos outros: identificar_planta
# não tem parâmetros que o Gemini preenche — a imagem vem de uma
# captura de câmera feita pelo CLIENTE (gemini/live_client_basic.py)
# antes de chamar despachar(), porque só o cliente sabe capturar um
# frame (reaproveitando vision/camera_capture.py). despachar() aqui
# espera argumentos = {"imagem_bytes": <bytes JPEG>}, nunca vindo do
# Gemini diretamente — ver INTEGRATION.md, seção
# "identificacao_planta", para o trecho exato de onde isso é
# injetado no cliente.
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="identificar_planta",
        description=(
            "Identifica a espécie de uma planta através de uma foto "
            "da câmera, usando uma API especializada em botânica "
            "(Pl@ntNet) — muito mais precisa que a visão geral para "
            "esse caso específico. Use somente quando o usuário "
            "pedir explicitamente para identificar a espécie ou o "
            "nome de uma planta (ex: 'que planta é essa', "
            "'identifica essa planta pra mim', 'qual o nome dessa "
            "espécie'). Para qualquer outra pergunta sobre o que a "
            "câmera está mostrando (objeto genérico, cor, "
            "contagem, etc.), não use esta função — responda "
            "normalmente com sua própria visão, como já faz hoje. "
            "Sem parâmetros: a captura da câmera é feita "
            "automaticamente ao chamar esta função."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string, pronta para o Jarvis falar). Se não reconhecer, retorna
# None. Síncrona/bloqueante de propósito (chamada de rede ao
# Pl@ntNet) — quem chama é responsável por rodar isso fora do event
# loop (asyncio.to_thread), igual aos outros pacotes.
def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "identificar_planta":
        return identificar_planta(argumentos.get("imagem_bytes"))

    return None


def identificar_planta(imagem_bytes):
    sucesso, resultado = plantnet_client.identificar(imagem_bytes)

    if not sucesso:
        return f"Falha ao identificar a planta: {resultado}"

    return _formatar_resultado(resultado)


def _formatar_resultado(candidatos):
    linhas = []

    for candidato in candidatos:
        nome_cientifico = candidato["nome_cientifico"]
        nomes_populares = candidato["nomes_populares"]
        confianca_pct = round(candidato["confianca"] * 100)

        nome_popular_texto = (
            f" ({nomes_populares[0]})" if nomes_populares else ""
        )

        linhas.append(
            f"{nome_cientifico}{nome_popular_texto}: {confianca_pct}% "
            "de confiança"
        )

    return (
        "Espécies candidatas identificadas pelo Pl@ntNet, da mais "
        "para a menos provável: " + "; ".join(linhas) + "."
    )
