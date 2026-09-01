# Pensar: manda a conversa (com as ferramentas do projeto) para a
# Mistral e devolve o texto final falado, executando as ferramentas
# que o modelo pedir pelo caminho.
#
# O laço de chamada de ferramenta segue o protocolo padrão da API
# estilo OpenAI: o modelo responde com tool_calls, o resultado de
# cada uma volta como uma mensagem role="tool" com o tool_call_id
# correspondente, e o modelo é chamado de novo até produzir texto.
# MAXIMO_RODADAS_FERRAMENTA limita isso para o modelo nunca ficar
# preso pedindo função sem nunca concluir.
import json
import time

import requests

# Instrução de sistema do modo reserva — centralizada em
# jarvis/nucleo/prompts/, seção CEREBRO_RESERVA (ver lá o porquê de
# não repetir a instrução de sistema completa do Gemini Live).
from jarvis.nucleo import prompts

from . import config, esquema, ferramentas_locais

# Mantido com o nome antigo por compatibilidade de leitura deste
# arquivo — o texto em si mora em prompts.CEREBRO_RESERVA_INSTRUCAO_SISTEMA.
INSTRUCAO_SISTEMA = prompts.CEREBRO_RESERVA_INSTRUCAO_SISTEMA


def _mensagem_sistema():
    return {"role": "system", "content": INSTRUCAO_SISTEMA}


# Uma requisição à API. Devolve (sucesso, mensagem_ou_erro), onde
# mensagem é o dict "message" da resposta.
def _chamar(mensagens, ferramentas, tentar_de_novo=True):
    if not config.MISTRAL_API_KEY:
        return False, "MISTRAL_API_KEY não configurada no .env."

    corpo = {
        "model": config.MODELO_CEREBRO,
        "messages": mensagens,
        "temperature": 0.4,
    }

    if ferramentas:
        corpo["tools"] = ferramentas
        corpo["tool_choice"] = "auto"

    try:
        resposta = requests.post(
            config.URL_MISTRAL_CHAT,
            headers={
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json=corpo,
            timeout=config.TIMEOUT_CEREBRO_SEGUNDOS,
        )

        if resposta.status_code == 429:
            # Limite por minuto. Com ~5,5k tokens de schema por
            # requisição, uma sequência rápida de perguntas encosta
            # nos 50k/min da Mistral — medido, não estimado. Em vez de
            # devolver uma desculpa na primeira vez, espera a janela
            # virar e tenta mais uma vez: para o usuário, isso vira
            # uma resposta um pouco mais lenta em vez de uma recusa.
            if tentar_de_novo:
                time.sleep(config.ESPERA_APOS_LIMITE_SEGUNDOS)

                return _chamar(
                    mensagens,
                    ferramentas,
                    tentar_de_novo=False,
                )

            return False, (
                "Muita coisa de uma vez agora. Repete daqui a pouco?"
            )

        if resposta.status_code != 200:
            return False, (
                f"O serviço respondeu com erro "
                f"(HTTP {resposta.status_code})."
            )

        return True, resposta.json()["choices"][0]["message"]

    except requests.Timeout:
        return False, "Tempo esgotado ao pensar na resposta."

    except requests.RequestException as erro:
        return False, f"Falha de conexão: {erro}"

    except (KeyError, IndexError, ValueError) as erro:
        return False, f"Resposta inesperada do serviço: {erro}"


# Processa um turno completo: recebe o histórico já com a fala nova
# do usuário no fim, executa quantas ferramentas forem necessárias e
# devolve (sucesso, texto_final, historico_atualizado, encerrar).
#
# encerrar=True quando o modelo chamou a ferramenta de encerrar a
# chamada: o texto ainda é falado normalmente (uma despedida), e só
# depois o modo reserva termina — ver assumir() em __init__.py.
#
# ao_executar_ferramenta(nome) é opcional e serve só para a interface
# mostrar o que está acontecendo — nunca influencia a conversa.
def responder(
    historico,
    pacotes_registrados,
    ferramentas,
    ao_executar_ferramenta=None,
):
    mensagens = [_mensagem_sistema()] + list(historico)
    encerrar = False

    for _ in range(config.MAXIMO_RODADAS_FERRAMENTA):
        sucesso, mensagem = _chamar(mensagens, ferramentas)

        if not sucesso:
            return False, mensagem, historico, encerrar

        chamadas = mensagem.get("tool_calls") or []

        if not chamadas:
            texto = (mensagem.get("content") or "").strip()

            if not texto:
                return False, (
                    "Não consegui formular uma resposta agora."
                ), historico, encerrar

            historico = list(historico) + [
                {"role": "assistant", "content": texto}
            ]

            return True, texto, historico, encerrar

        # O modelo pediu ferramentas: a mensagem dele precisa entrar
        # no histórico ANTES das respostas role="tool", senão a API
        # rejeita o tool_call_id como órfão.
        mensagens.append(
            {
                "role": "assistant",
                "content": mensagem.get("content") or "",
                "tool_calls": chamadas,
            }
        )

        for chamada in chamadas:
            funcao = chamada.get("function") or {}
            nome = funcao.get("name") or ""

            if ao_executar_ferramenta:
                ao_executar_ferramenta(nome)

            if nome == ferramentas_locais.NOME_ENCERRAR:
                # Não há nada a executar: encerrar é o fim da
                # conversa, não uma ação com resultado. O modelo
                # ainda produz a despedida na rodada seguinte.
                encerrar = True
                resultado = (
                    "A chamada vai ser encerrada. Despeça-se do "
                    "usuário em uma frase curta."
                )

            else:
                resultado = esquema.despachar_ferramenta(
                    pacotes_registrados,
                    nome,
                    funcao.get("arguments"),
                )

            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": chamada.get("id"),
                    "name": nome,
                    "content": str(resultado),
                }
            )

    # Estourou o limite de rodadas: devolve o que der, sem insistir.
    return False, (
        "Fiz o que consegui, mas não terminei essa ação agora."
    ), historico, encerrar


# Mantém o histórico curto. Nunca corta no meio de um par
# assistant/tool: só mensagens de conversa (user/assistant) são
# guardadas entre turnos, então o corte é sempre seguro.
def podar_historico(historico):
    limite = config.MAXIMO_MENSAGENS_HISTORICO

    if len(historico) <= limite:
        return historico

    return historico[-limite:]


def montar_ferramentas(pacotes_registrados):
    return esquema.montar_ferramentas(pacotes_registrados)


def descrever_json(valor):
    try:
        return json.dumps(valor, ensure_ascii=False)

    except (TypeError, ValueError):
        return str(valor)
