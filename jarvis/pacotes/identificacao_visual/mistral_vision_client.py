# Cliente do endpoint de chat completions da Mistral (La Plateforme)
# com entrada de imagem — usado como segunda opinião independente do
# Gemini para identificação de objeto genérico (não plantas — isso é
# jarvis/pacotes/identificacao_planta/Pl@ntNet).
#
# Formato de request confirmado na documentação oficial
# (docs.mistral.ai/capabilities/vision) antes de escrever qualquer
# código, nunca adivinhado: POST /v1/chat/completions, compatível
# com o formato da OpenAI, com o item de imagem no content sendo
# {"type": "image_url", "image_url": "<string>"} — o valor de
# image_url é uma STRING PLANA (uma URL pública OU uma data URI
# base64 'data:image/jpeg;base64,...'), não um objeto aninhado
# {"url": ...} como a OpenAI usa.
import base64

import requests

from . import config

_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"


# Envia a imagem (bytes JPEG já em memória — nunca gravada em disco)
# + a pergunta exata que o usuário fez pro modelo de visão atual da
# Mistral. Nunca lança exceção — sempre retorna (sucesso: bool,
# resultado):
#   sucesso=True  -> resultado é o texto da resposta da Mistral.
#   sucesso=False -> resultado já vem formatado como uma instrução
#                     pro Jarvis responder só com a própria visão e
#                     avisar o usuário que não conseguiu confirmar
#                     com uma segunda fonte desta vez — igual à
#                     convenção de 'segunda_opiniao' em
#                     jarvis/pacotes/delegacao_ia/roteador.py.
def consultar(imagem_bytes, pergunta):
    if not config.MISTRAL_API_KEY:
        return False, _mensagem_indisponivel(
            "MISTRAL_API_KEY não configurada no .env"
        )

    if not imagem_bytes:
        return False, _mensagem_indisponivel(
            "nenhuma imagem foi capturada da câmera"
        )

    imagem_base64 = base64.b64encode(imagem_bytes).decode("utf-8")

    try:
        resposta = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.MODELO_MISTRAL_VISION,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": pergunta or "O que é isso na imagem?",
                            },
                            {
                                "type": "image_url",
                                "image_url": f"data:image/jpeg;base64,{imagem_base64}",
                            },
                        ],
                    }
                ],
            },
            timeout=config.TIMEOUT_SEGUNDOS,
        )

    except requests.Timeout:
        return False, _mensagem_indisponivel(
            "tempo esgotado ao consultar a Mistral"
        )

    except requests.RequestException as erro:
        return False, _mensagem_indisponivel(
            f"falha de conexão com a Mistral ({erro})"
        )

    if resposta.status_code == 401:
        return False, _mensagem_indisponivel(
            "chave de API da Mistral inválida ou expirada"
        )

    if resposta.status_code == 429:
        # O tier gratuito da Mistral tem poucas requisições por
        # minuto — vale tratar isso como um caso esperado, não uma
        # falha genérica.
        return False, _mensagem_indisponivel(
            "limite de requisições por minuto da Mistral atingido "
            "(comum no tier gratuito)"
        )

    if resposta.status_code != 200:
        return False, _mensagem_indisponivel(
            f"a Mistral retornou um erro (HTTP {resposta.status_code})"
        )

    try:
        dados = resposta.json()
        texto = dados["choices"][0]["message"]["content"]

    except (ValueError, KeyError, IndexError) as erro:
        return False, _mensagem_indisponivel(
            f"resposta inesperada da Mistral ({erro})"
        )

    return True, texto.strip()


def _mensagem_indisponivel(motivo):
    return (
        f"Não foi possível obter uma segunda opinião da Mistral "
        f"({motivo}). Responda usando só sua própria visão e avise "
        "o usuário que não conseguiu confirmar com uma segunda "
        "fonte desta vez."
    )
