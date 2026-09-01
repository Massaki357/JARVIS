# Cliente do Pl@ntNet (my.plantnet.org) — API especializada em
# identificação de espécies vegetais por foto. Usada só para essa
# tarefa específica: identificação de espécie não é o forte de
# modelos de visão generalistas como o Gemini, então esta tool
# substitui o Gemini apenas nesse caso, não a visão geral da câmera.
#
# Formato de request confirmado na documentação oficial —
# my.plantnet.org/doc/api/identify e o exemplo oficial em
# github.com/plantnet/my.plantnet/blob/master/examples/post/run.py —
# nunca adivinhado:
#   POST https://my-api.plantnet.org/v2/identify/{project}?api-key=...
#   multipart/form-data, imagem no campo 'images' (repetível pra
#   mais de uma imagem — aqui sempre mandamos só uma).
# O parâmetro 'organs' é opcional; a documentação confirma que
# omiti-lo define automaticamente 'auto' (detecção automática do
# órgão da planta) para cada imagem — comportamento certo aqui, já
# que a câmera captura uma foto genérica sem saber se é folha, flor,
# fruto ou casca.
import requests

from . import config

_ENDPOINT_BASE = "https://my-api.plantnet.org/v2/identify"


# Envia UMA imagem (bytes JPEG já em memória — nunca gravada em
# disco) pro Pl@ntNet e retorna as espécies candidatas mais
# prováveis. Nunca lança exceção — sempre retorna (sucesso: bool,
# resultado):
#   sucesso=True  -> resultado é uma lista de até
#                     config.QUANTIDADE_RESULTADOS dicts
#                     {"nome_cientifico", "nomes_populares",
#                     "confianca"}, na mesma ordem (decrescente por
#                     confiança) que a API já devolve.
#   sucesso=False -> resultado é uma string em português explicando
#                     o que deu errado, pronta pro Jarvis falar.
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
