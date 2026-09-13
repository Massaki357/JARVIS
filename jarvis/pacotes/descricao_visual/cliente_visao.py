# Cliente de imagem-para-texto: recebe uma imagem já capturada (bytes
# JPEG em memória, nunca gravada em disco) e devolve a descrição em
# texto.
#
# DOIS PROVEDORES, escolhidos por config.provedor_visao():
#
#   "gemini"  (padrão) — a mesma GEMINI_API_KEY que o projeto já exige
#             para funcionar.
#   "mistral" — reaproveitando a MISTRAL_API_KEY de
#             jarvis/pacotes/identificacao_visual/.
#
# POR QUE O PADRÃO É O GEMINI, e não a Mistral (que seria o
# reaproveitamento mais óbvio, já que identificacao_visual usa visão
# da Mistral e está verificada): medido ao vivo enquanto este pacote
# era escrito, a chave da Mistral deste projeto responde 429 com
# "x-ratelimit-limit-req-minute: 0" — o limite é ZERO, não um throttle
# passageiro; a cota do tier gratuito acabou. O Gemini descreveu um
# print real de 467 KB em 5,7s na mesma hora. Entregar o padrão numa
# chave sem cota seria entregar uma ferramenta que não funciona.
#
# Trocar de provedor é uma variável no .env — nenhum código muda. Se
# a cota da Mistral voltar e você preferir tirar mais essa carga do
# Gemini, DESCRICAO_VISUAL_PROVEDOR=mistral resolve.
#
# ATENÇÃO: o padrão DESTE pacote é fixo em "gemini", diferente de
# jarvis/pacotes/identificacao_visual/, cujo padrão automático é
# sempre o provedor OPOSTO ao cérebro de voz ativo. O motivo da
# assimetria está no cabeçalho de config.py: descrever_tela/
# descrever_camera não são uma segunda opinião, são a visão primária,
# e não têm nenhuma independência a preservar.
#
# UM CAMINHO SÓ PARA OS DOIS PROVEDORES. Antes deste arquivo passar
# por jarvis/servicos/agentes/ (LangChain), ele tinha duas
# implementações inteiras lado a lado — _descrever_gemini com o SDK
# google-genai e timeout em milissegundos, _descrever_mistral com
# requests.post e o formato de imagem próprio da Mistral (image_url
# como STRING PLANA, não o objeto {"url": ...} da OpenAI; errar essa
# forma não falhava de modo óbvio, e por isso estava anotado aqui).
# Hoje o provedor é UM CAMPO do pedido, e a diferença de protocolo é
# problema do LangChain.
from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

# Qual chave e qual modelo cada provedor usa. As variáveis continuam
# sendo as mesmas de sempre, no config.py deste pacote — a camada de
# agentes nunca lê .env por conta própria.
_PROVEDORES = {
    "gemini": ("GEMINI_API_KEY", "MODELO_GEMINI"),
    "mistral": ("MISTRAL_API_KEY", "MODELO_MISTRAL"),
}


# Devolve (sucesso, texto). Nunca levanta exceção — mesma convenção
# de todo pacote deste projeto.
#
# Em caso de falha, o texto já vem pronto para ser dito ao usuário:
# aqui a descrição é a resposta inteira do turno, então esconder a
# falha deixaria o assistente mudo sem explicação. É o oposto da
# convenção de identificacao_visual, onde a falha instrui o cérebro a
# responder com a própria visão — aqui não existe visão própria.
def descrever(imagem_bytes, pergunta, origem):
    if not imagem_bytes:
        return False, _falha(origem, "nenhuma imagem foi capturada")

    texto_pergunta = (pergunta or "").strip() or (
        prompts.DESCRICAO_VISUAL_PERGUNTA_PADRAO.format(origem=origem)
    )

    # Resolvido a cada chamada (nunca fixado na importação): assim
    # tanto a variável manual quanto a regra automática valem já na
    # próxima chamada, sem reiniciar o app.
    provedor = config.provedor_visao()

    if provedor not in _PROVEDORES:
        provedor = "gemini"

    nome_chave, nome_modelo = _PROVEDORES[provedor]
    api_key = getattr(config, nome_chave, None)

    if not api_key:
        return False, _falha(
            origem, f"a {nome_chave} não está configurada"
        )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor=provedor,
            modelo=getattr(config, nome_modelo),
            api_key=api_key,
            texto=texto_pergunta,
            imagem=imagem_bytes,
            instrucao_sistema=prompts.DESCRICAO_VISUAL_INSTRUCAO,
            # TIMEOUT OBRIGATÓRIO, em SEGUNDOS. Esta chamada roda na
            # thread do roteamento, dentro de um asyncio.to_thread que
            # também não tem wait_for por fora — uma chamada pendurada
            # travaria o turno de voz para sempre, sem levantar nada.
            # É a mesma classe de travamento silencioso já corrigida
            # várias vezes neste projeto, e a camada de agentes a
            # torna impossível: não existe modelo sem timeout.
            timeout=config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="descricao_visual"),
    )

    if not resposta.sucesso:
        return False, _falha(origem, _motivo_do_erro(resposta, provedor))

    if not resposta.texto:
        return False, _falha(origem, "a descrição voltou vazia")

    return True, resposta.texto


# Traduz a falha para o motivo que o usuário vai ouvir.
#
# Mesma lição já aprendida no roteamento hierárquico: sem o detalhe
# real, um erro recuperável fica indistinguível de qualquer outro.
# Em especial o 429 da Mistral, que significa duas coisas diferentes:
# quando o cabeçalho diz que o limite por minuto é 0, mandar esperar
# seria mandar esperar por algo que não vai reabrir sozinho.
def _motivo_do_erro(resposta, provedor):
    if resposta.tipo_erro == agentes.erros.TEMPO:
        return (
            f"o modelo de visão demorou mais de "
            f"{config.TIMEOUT_SEGUNDOS}s"
        )

    if resposta.tipo_erro == agentes.erros.AUTENTICACAO:
        return f"a chave de API da {provedor} é inválida ou expirou"

    if resposta.tipo_erro == agentes.erros.LIMITE:
        limite = resposta.cabecalho_do_erro("x-ratelimit-limit-req-minute")

        if limite is not None and str(limite).strip() in ("0", "0.0"):
            return (
                f"a chave da {provedor} está sem cota disponível "
                "(limite por minuto zerado, não é espera passageira)"
            )

        return (
            f"o limite de requisições por minuto da {provedor} foi "
            "atingido"
        )

    return f"o modelo de visão falhou ({resposta.erro})"


def _falha(origem, motivo):
    return prompts.DESCRICAO_VISUAL_INDISPONIVEL.format(
        origem=origem,
        motivo=motivo,
    )
