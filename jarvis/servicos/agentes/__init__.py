"""
Camada de agentes do ALFRED — o LangChain como caminho ÚNICO para
falar com qualquer LLM de texto ou de visão deste projeto.

COMO USAR (é sempre isto, em qualquer pacote)
=============================================

    from jarvis.servicos import agentes

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="groq",                 # ou gemini/openai/cerebras/mistral
            modelo=config.MODELO_GROQ,
            api_key=config.GROQ_API_KEY,     # sempre do config.py de QUEM CHAMA
            texto=pergunta,
            timeout=config.TIMEOUT_SEGUNDOS, # em SEGUNDOS, sempre
        )
    )

    if not resposta.sucesso:
        return False, f"Não deu certo: {resposta.erro}"

    return True, resposta.texto

Com imagem, é o mesmo pedido com `imagem=bytes_jpeg`. Com
ferramentas, é o mesmo pedido com `ferramentas=<esquemas>` e a
resposta em `resposta.primeira_chamada()`. Com JSON, é
`json_esperado=True` e a resposta já decodificada em `resposta.dados`.
Nenhum desses casos tem um formato próprio: é sempre PedidoAgente
entrando e RespostaAgente saindo.

O QUE ESTA CAMADA NÃO COBRE, DE PROPÓSITO
=========================================

Os três CÉREBROS DE VOZ (jarvis/cerebro/): Gemini Live, OpenAI
Realtime e o servidor local via MQTT. Eles não são chamadas de
pedido-e-resposta: são sessões de ÁUDIO BIDIRECIONAL em tempo real,
com interrupção, VAD, transcrição incremental e retomada de sessão.
O LangChain não modela esse tipo de sessão, e reescrevê-los aqui
significaria reimplementar o protocolo dos dois por cima de uma
abstração que não o representa.

O que os cérebros GANHAM com esta camada é indireto e real: toda
ferramenta que eles despacham e que por sua vez consulta outra LLM
(delegar_tarefa, consultar_segunda_opiniao_visual, descrever_tela,
identificar planta, consolidar memória, localizar elemento na tela)
agora atravessa um caminho só.

Também ficam de fora as integrações que NÃO são LLM, mesmo sendo
HTTP: o Pl@ntNet de jarvis/pacotes/identificacao_planta/ (API de
catálogo botânico, sem prompt nenhum) e a busca de
jarvis/pacotes/pesquisa_web/ (ddgs).

SOBRE O ISOLAMENTO DOS PACOTES
==============================

Vários pacotes que passaram a importar esta camada são descritos no
CLAUDE.md como deliberadamente autossuficientes, "para serem
copiados para outro projeto como estão". Importar jarvis.servicos.
agentes vai contra esse princípio — a mesma tensão já registrada
quando os prompts foram centralizados em jarvis/nucleo/prompts/, e
resolvida do mesmo jeito: a padronização foi pedida explicitamente,
então foi feita. Se um desses pacotes for mesmo extraído um dia,
esta pasta precisa ir junto (ou a chamada volta a ser inline naquele
momento).

VARIÁVEIS DE .ENV: esta camada não lê nenhuma, de propósito — e por
isso não tem config_schema() nem entra em PACOTES_COM_CONFIG. Chave,
modelo e timeout chegam prontos de quem chama, para cada pacote
continuar dono das próprias variáveis e a tela de configurações
continuar mostrando cada uma na seção onde o usuário espera achá-la.
"""

from .agente import (
    ChamadaFerramenta,
    PedidoAgente,
    PoliticaRepeticao,
    RespostaAgente,
    UsoTokens,
    executar,
)
from .modelos import PROVEDORES_SUPORTADOS, criar_modelo

from . import erros
from . import ferramentas
from . import mensagens

__all__ = [
    "ChamadaFerramenta",
    "PedidoAgente",
    "PoliticaRepeticao",
    "RespostaAgente",
    "UsoTokens",
    "executar",
    "criar_modelo",
    "PROVEDORES_SUPORTADOS",
    "erros",
    "ferramentas",
    "mensagens",
]
