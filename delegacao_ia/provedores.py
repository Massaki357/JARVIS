# requests é suficiente aqui: Groq, Cerebras e OpenAI expõem uma API
# de completions compatível com o formato da OpenAI
# (POST .../chat/completions), então não precisamos de um SDK
# diferente por provedor.
import requests

from . import config


# Faz uma chamada de completions simples (sem streaming) a um
# endpoint compatível com a API da OpenAI. Nunca lança exceção —
# sempre retorna (sucesso: bool, texto_ou_mensagem_de_erro: str).
def _chamar_completions(url, api_key, modelo, prompt):
    try:
        resposta = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": modelo,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "stream": False,
            },
            timeout=config.TIMEOUT_SEGUNDOS,
        )

        resposta.raise_for_status()

        dados = resposta.json()

        texto = dados["choices"][0]["message"]["content"]

        return True, texto.strip()

    except requests.Timeout:
        return False, "Tempo esgotado ao consultar o provedor."

    except requests.RequestException as erro:
        return False, f"Falha na chamada ao provedor: {erro}"

    except (KeyError, IndexError, ValueError) as erro:
        return False, f"Resposta inesperada do provedor: {erro}"


def consultar_groq(prompt):
    if not config.GROQ_API_KEY:
        return False, "GROQ_API_KEY não configurada no .env."

    return _chamar_completions(
        "https://api.groq.com/openai/v1/chat/completions",
        config.GROQ_API_KEY,
        config.MODELO_GROQ,
        prompt,
    )


def consultar_cerebras(prompt):
    if not config.CEREBRAS_API_KEY:
        return False, "CEREBRAS_API_KEY não configurada no .env."

    return _chamar_completions(
        "https://api.cerebras.ai/v1/chat/completions",
        config.CEREBRAS_API_KEY,
        config.MODELO_CEREBRAS,
        prompt,
    )


def consultar_openai(prompt):
    if not config.OPENAI_API_KEY:
        return False, "OPENAI_API_KEY não configurada no .env."

    return _chamar_completions(
        "https://api.openai.com/v1/chat/completions",
        config.OPENAI_API_KEY,
        config.MODELO_OPENAI,
        prompt,
    )
