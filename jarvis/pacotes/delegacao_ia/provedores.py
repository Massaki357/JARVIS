# requests é suficiente aqui: Groq, Cerebras e OpenAI expõem uma API
# de completions compatível com o formato da OpenAI
# (POST .../chat/completions), então não precisamos de um SDK
# diferente por provedor.
import requests

from . import config


# Faz uma chamada de completions simples (sem streaming) a um
# endpoint compatível com a API da OpenAI. Nunca lança exceção —
# sempre retorna (sucesso: bool, texto_ou_mensagem_de_erro: str).
def _chamar_completions(
    url,
    api_key,
    modelo,
    prompt,
    json_esperado=False,
    timeout=None,
):
    corpo = {
        "model": modelo,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
    }

    # Modo JSON nativo do provedor. Quem pede isto (a criação de
    # perfil) já valida o JSON em código de qualquer jeito — isto só
    # reduz a chance de vir texto solto em volta, não substitui a
    # validação.
    if json_esperado:
        corpo["response_format"] = {"type": "json_object"}

    try:
        resposta = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=corpo,
            timeout=timeout or config.TIMEOUT_SEGUNDOS,
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


def consultar_openai(prompt, json_esperado=False, timeout=None):
    if not config.OPENAI_API_KEY:
        return False, "OPENAI_API_KEY não configurada no .env."

    return _chamar_completions(
        "https://api.openai.com/v1/chat/completions",
        config.OPENAI_API_KEY,
        config.MODELO_OPENAI,
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_gemini(prompt, json_esperado=False, timeout=None):
    """
    Consulta o Gemini. Mesma assinatura e mesmo contrato dos outros
    três — (sucesso, texto_ou_erro), nunca levanta exceção.

    Não passa por _chamar_completions porque o Gemini NÃO expõe a API
    no formato da OpenAI: usa o SDK google-genai, que o projeto já
    tem como dependência obrigatória.
    """
    if not config.GEMINI_API_KEY:
        return False, "GEMINI_API_KEY não configurada no .env."

    try:
        from google import genai
        from google.genai import types

        cliente = genai.Client(api_key=config.GEMINI_API_KEY)

        opcoes = {
            "http_options": types.HttpOptions(
                timeout=(timeout or config.TIMEOUT_SEGUNDOS) * 1000
            ),
            # Sem isto o SDK imprime um aviso sobre "automatic function
            # calling" a cada chamada — barulho que cairia direto no
            # painel de console do app, que duplica o stdout. Não
            # usamos AFC aqui: queremos texto de volta, não chamada de
            # função.
            "automatic_function_calling": (
                types.AutomaticFunctionCallingConfig(disable=True)
            ),
        }

        if json_esperado:
            opcoes["response_mime_type"] = "application/json"

        resposta = cliente.models.generate_content(
            model=config.MODELO_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(**opcoes),
        )

        texto = (getattr(resposta, "text", "") or "").strip()

        if not texto:
            return False, "O Gemini devolveu uma resposta vazia."

        return True, texto

    except Exception as erro:
        return False, f"Falha na chamada ao Gemini: {erro}"
