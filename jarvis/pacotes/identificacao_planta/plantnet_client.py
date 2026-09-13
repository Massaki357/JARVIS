import requests

from . import config

_ENDPOINT_BASE = "https://my-api.plantnet.org/v2/identify"


def identificar(imagem_bytes):
    if not config.PLANTNET_API_KEY:
        return False, "A chave de API do Pl@ntNet (PLANTNET_API_KEY) não está configurada no .env."

    if not imagem_bytes:
        return False, "Nenhuma imagem foi capturada para enviar ao Pl@ntNet."

    url = f"{_ENDPOINT_BASE}/{config.PROJETO_PLANTNET}"

    try:
        resposta = requests.post(
            url,
            params={"api-key": config.PLANTNET_API_KEY},
            files=[
                ("images", ("camera.jpg", imagem_bytes, "image/jpeg")),
            ],
            timeout=config.TIMEOUT_SEGUNDOS,
        )

    except requests.RequestException as erro:
        return False, f"Falha ao conectar com o Pl@ntNet: {erro}"

    if resposta.status_code != 200:
        return False, _mensagem_erro(resposta)

    try:
        dados = resposta.json()

    except ValueError:
        return False, "O Pl@ntNet retornou uma resposta que não é JSON válido."

    resultados = dados.get("results") or []

    if not resultados:
        return False, "O Pl@ntNet não encontrou nenhuma espécie compatível com a imagem."

    candidatos = []

    for item in resultados[: config.QUANTIDADE_RESULTADOS]:
        especie = item.get("species") or {}

        nome_cientifico = (
            especie.get("scientificNameWithoutAuthor")
            or especie.get("scientificName")
            or "espécie desconhecida"
        )

        candidatos.append(
            {
                "nome_cientifico": nome_cientifico,
                "nomes_populares": especie.get("commonNames") or [],
                "confianca": item.get("score") or 0.0,
            }
        )

    return True, candidatos


def _mensagem_erro(resposta):
    try:
        corpo = resposta.json()
        detalhe = corpo.get("message") or corpo.get("error") or str(corpo)

    except ValueError:
        detalhe = (resposta.text or "").strip()[:200]

    if resposta.status_code == 401:
        return f"Chave de API do Pl@ntNet inválida ou expirada ({detalhe})."

    if resposta.status_code == 404:
        return "O Pl@ntNet não encontrou nenhuma espécie compatível com a imagem."

    if resposta.status_code == 429:
        return f"Limite diário de identificações do Pl@ntNet atingido ({detalhe})."

    return f"O Pl@ntNet retornou um erro (HTTP {resposta.status_code}): {detalhe}"
