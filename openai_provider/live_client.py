"""
Worker equivalente a gemini/live_client.py, mas usando a Realtime API
da OpenAI como "cérebro" do ALFRED em vez do Gemini Live.

Mantém a mesma API pública (sinais, construtor, métodos) do
GeminiLiveWorker para que ui/main_window.py possa trocar de provedor
apenas alterando core.config.PROVEDOR_IA, sem tocar na interface.
"""

import asyncio
import base64
import json
import time
from datetime import datetime
from array import array

import sounddevice as sd

from PySide6.QtCore import QThread, Signal

from openai import AsyncOpenAI

from core.config import (
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_VOICE,
)

from vision.screen_capture import capturar_tela_bytes
from vision.camera_capture import capturar_camera_bytes

from actions.file_actions import (
    criar_pasta_area_trabalho,
    listar_area_de_trabalho,
    organizar_area_de_trabalho_basico,
    copiar_item_area_trabalho,
    recortar_item_area_trabalho,
    colar_item_area_trabalho,
    renomear_item_area_trabalho,
    cancelar_transferencia_area_trabalho,
)
from actions.app_actions import abrir_aplicativo
from actions.browser_actions import (
    pesquisar_no_navegador,
    tocar_no_youtube,
)
from actions.web_search import (
    avaliar_necessidade_pesquisa,
    pesquisar_informacao_atual,
    resposta_sem_pesquisa,
)
from actions.mouse_actions import (
    rolar_pagina,
    clicar_mouse,
    duplo_clique_mouse,
    clique_direito_mouse,
    mover_e_clicar,
)
from vision.click_locator import localizar_elemento_na_tela
from memory.memory_manager import (
    salvar_memoria,
    listar_memorias,
    esquecer_memoria,
    contexto_memorias,
)
from actions.agenda_actions import (
    criar_evento_agenda,
    listar_agenda,
    cancelar_evento_agenda,
)
from actions.text_actions import escrever_no_campo_ativo
from actions.consulta_acoes_action import (
    consultar_cotacao,
    consultar_historico,
)


# A Realtime API da OpenAI trabalha em PCM16 24 kHz tanto na entrada
# quanto na saída, por isso as duas taxas são iguais aqui (no Gemini
# a entrada é 16 kHz e a saída 24 kHz).
TAXA_ENTRADA = 24000
TAXA_SAIDA = 24000
CANAIS = 1
BLOCO = 1024

ATRASO_REABRIR_MICROFONE = 0.8
LIMITE_FILA_MICROFONE = 50
COOLDOWN_FUNCAO_VISUAL = 8.0


def _tool(nome, descricao, propriedades=None, obrigatorios=None):
    """Monta uma declaração de função no formato da Realtime API."""

    return {
        "type": "function",
        "name": nome,
        "description": descricao,
        "parameters": {
            "type": "object",
            "properties": propriedades or {},
            "required": obrigatorios or [],
        },
    }


class OpenAILiveWorker(QThread):

    status_recebido = Signal(str)
    erro_recebido = Signal(str)
    chamada_encerrada = Signal()
    nivel_audio = Signal(float)
    solicitou_encerramento = Signal()

    # A Realtime API da OpenAI não possui um equivalente direto ao
    # GoAway/session_resumption do Gemini. Os sinais existem apenas
    # para manter a mesma interface do GeminiLiveWorker; não são
    # emitidos por este worker.
    solicitou_reconexao = Signal()
    session_handle_atualizado = Signal(str)

    def __init__(self, session_handle=None):
        super().__init__()

        self.ativo = True
        self.loop = None
        self.conexao = None
        # Mantido apenas por compatibilidade de assinatura com o
        # GeminiLiveWorker. A OpenAI Realtime não retoma sessões por
        # handle, então este valor nunca é usado para reconectar.
        self.session_handle = session_handle

        self.processando_ferramenta = False
        self.lock_envio = None
        self.imagem_visual_pendente = None

        self.alfred_falando = False
        self.tarefa_liberar_microfone = None
        self.tarefa_encerramento = None

        self.executando_funcao_visual = False
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        self.silenciar_audio_ate_fim_turno = False

    def run(self):
        try:
            asyncio.run(self.executar())
        except Exception as erro:
            self.erro_recebido.emit(str(erro))
        finally:
            self.nivel_audio.emit(0.0)
            self.chamada_encerrada.emit()

    def _construir_ferramentas(self):
        return [
            _tool(
                "analisar_tela",
                "Use esta função somente quando o usuário pedir "
                "explicitamente para analisar, ver, observar ou "
                "explicar a tela do computador. Não use "
                "espontaneamente e não repita para o mesmo pedido.",
            ),
            _tool(
                "analisar_camera",
                "Use esta função somente quando o usuário pedir "
                "explicitamente para analisar, ver, observar ou "
                "explicar a webcam ou câmera. Não use "
                "espontaneamente e não repita para o mesmo pedido.",
            ),
            _tool(
                "criar_pasta_area_trabalho",
                "Cria uma pasta nova na área de trabalho do Windows. "
                "Use quando o usuário pedir para criar uma pasta. "
                "Nunca sobrescreva nada.",
                {"nome": {"type": "string", "description": "Nome da pasta a ser criada."}},
                ["nome"],
            ),
            _tool(
                "listar_area_de_trabalho",
                "Lista os itens presentes na área de trabalho do Windows.",
            ),
            _tool(
                "organizar_area_de_trabalho_basico",
                "Organiza arquivos soltos da área de trabalho em pastas "
                "por tipo, como Imagens, PDFs, Documentos e Compactados. "
                "Nunca exclui arquivos e nunca sobrescreve arquivos "
                "existentes.",
            ),
            _tool(
                "copiar_item_area_trabalho",
                "Prepara um arquivo ou pasta da Área de Trabalho para ser "
                "copiado. Use quando o usuário disser copiar. Depois, use "
                "colar_item_area_trabalho quando ele indicar o destino. "
                "Nunca sobrescreve itens.",
                {
                    "nome": {
                        "type": "string",
                        "description": "Nome do arquivo ou pasta que será copiado.",
                    },
                    "pasta_origem": {
                        "type": "string",
                        "description": (
                            "Pasta relativa dentro da Área de Trabalho. Use "
                            "vazio quando o item estiver diretamente na "
                            "Área de Trabalho."
                        ),
                    },
                },
                ["nome"],
            ),
            _tool(
                "recortar_item_area_trabalho",
                "Prepara um arquivo ou pasta da Área de Trabalho para ser "
                "movido. Use quando o usuário disser recortar ou mover. "
                "Depois, use colar_item_area_trabalho quando ele indicar o "
                "destino. Nunca sobrescreve itens.",
                {
                    "nome": {
                        "type": "string",
                        "description": "Nome do arquivo ou pasta que será recortado.",
                    },
                    "pasta_origem": {
                        "type": "string",
                        "description": (
                            "Pasta relativa dentro da Área de Trabalho. Use "
                            "vazio quando o item estiver diretamente na "
                            "Área de Trabalho."
                        ),
                    },
                },
                ["nome"],
            ),
            _tool(
                "colar_item_area_trabalho",
                "Cola o último arquivo ou pasta preparado por copiar ou "
                "recortar. O destino deve ser uma pasta dentro da Área de "
                "Trabalho. Use destino vazio para colar na raiz da Área de "
                "Trabalho. Nunca sobrescreve itens.",
                {
                    "pasta_destino": {
                        "type": "string",
                        "description": (
                            "Caminho relativo da pasta de destino dentro da "
                            "Área de Trabalho. Exemplo: Projetos/Cliente. "
                            "Use vazio para a raiz da Área de Trabalho."
                        ),
                    },
                },
            ),
            _tool(
                "renomear_item_area_trabalho",
                "Renomeia um arquivo ou pasta existente dentro da Área de "
                "Trabalho. Use somente quando o usuário informar "
                "claramente o nome atual e o novo nome. Nunca sobrescreve.",
                {
                    "nome_atual": {
                        "type": "string",
                        "description": "Nome atual do arquivo ou pasta.",
                    },
                    "novo_nome": {
                        "type": "string",
                        "description": "Novo nome desejado.",
                    },
                    "pasta_origem": {
                        "type": "string",
                        "description": (
                            "Pasta relativa dentro da Área de Trabalho. Use "
                            "vazio quando o item estiver diretamente na "
                            "Área de Trabalho."
                        ),
                    },
                },
                ["nome_atual", "novo_nome"],
            ),
            _tool(
                "cancelar_transferencia_area_trabalho",
                "Cancela o último copiar ou recortar que ainda não foi "
                "colado. Use quando o usuário pedir para cancelar a "
                "operação de arquivo.",
            ),
            _tool(
                "criar_evento_agenda",
                "Salva um compromisso na agenda local persistente do "
                "ALFRED. Use quando o usuário pedir para agendar, marcar "
                "ou anotar um compromisso para uma data e horário "
                "específicos. Converta a data para o formato "
                "YYYY-MM-DD HH:MM. Esta função não cria alarmes.",
                {
                    "titulo": {
                        "type": "string",
                        "description": "Descrição curta do compromisso.",
                    },
                    "data_hora": {
                        "type": "string",
                        "description": "Data e hora local no formato YYYY-MM-DD HH:MM.",
                    },
                },
                ["titulo", "data_hora"],
            ),
            _tool(
                "listar_agenda",
                "Lista os próximos compromissos salvos na agenda. Use "
                "quando o usuário perguntar o que está agendado, quais "
                "são os próximos compromissos.",
            ),
            _tool(
                "cancelar_evento_agenda",
                "Cancela um compromisso da agenda. Use somente quando o "
                "usuário pedir claramente para cancelar. Aceita o número "
                "do compromisso ou parte do título.",
                {
                    "referencia": {
                        "type": "string",
                        "description": "Número ou trecho do nome do compromisso.",
                    },
                },
                ["referencia"],
            ),
            _tool(
                "abrir_aplicativo",
                "Abre aplicativos, programas ou locais permitidos do "
                "Windows, como meu computador, explorador de arquivos, "
                "navegador, Google, Chrome, Edge, antivírus, Windows "
                "Defender, configurações ou painel de controle.",
                {
                    "nome": {
                        "type": "string",
                        "description": "Nome do aplicativo, programa ou local a abrir.",
                    },
                },
                ["nome"],
            ),
            _tool(
                "pesquisar_no_navegador",
                "Abre uma pesquisa no Google usando o navegador padrão. "
                "Use somente quando o usuário pedir explicitamente para "
                "abrir, mostrar ou fazer a pesquisa no navegador ou no "
                "Google. Exemplos: 'pesquise no Google', 'abra no "
                "navegador', 'mostre os resultados no navegador'. Não use "
                "para perguntas que devem ser respondidas por voz, como "
                "preço do dólar, previsão, explicações ou dúvidas gerais. "
                "Não use para tocar músicas ou vídeos.",
                {
                    "consulta": {
                        "type": "string",
                        "description": "Texto exato que deve ser pesquisado no Google.",
                    },
                },
                ["consulta"],
            ),
            _tool(
                "pesquisar_informacao_atual",
                "Use esta função SOMENTE quando a pergunta exigir "
                "informação atual ou variável. Exemplos permitidos: "
                "cotação de moedas, jogos e placares, clima, notícias, "
                "preços atuais, resultados recentes, lançamentos, versões "
                "atuais e ocupantes atuais de cargos. NÃO use para "
                "definições, explicações, programação, matemática, "
                "biografias históricas ou conhecimentos estáveis. "
                "Exemplos proibidos: 'o que é Python?', 'quem foi Albert "
                "Einstein?' e 'como funciona um motor?'. Na dúvida, "
                "responda sem pesquisar.",
                {
                    "consulta": {
                        "type": "string",
                        "description": (
                            "Consulta curta e objetiva que contenha o "
                            "assunto atual, data, local ou equipe."
                        ),
                    },
                },
                ["consulta"],
            ),
            _tool(
                "tocar_no_youtube",
                "Pesquisa e abre no YouTube uma música ou vídeo para "
                "reprodução no navegador padrão. Use quando o usuário "
                "pedir claramente para tocar, reproduzir, colocar ou "
                "ouvir uma música ou vídeo no YouTube. Exemplos: 'toque "
                "One do Metallica no YouTube', 'reproduza Bohemian "
                "Rhapsody no YouTube'. Não use para perguntas sobre "
                "músicas nem para pesquisas comuns no Google.",
                {
                    "busca": {
                        "type": "string",
                        "description": (
                            "Nome da música, artista ou vídeo que deve ser "
                            "aberto no YouTube."
                        ),
                    },
                },
                ["busca"],
            ),
            _tool(
                "escrever_no_campo_ativo",
                "Insere texto exatamente no campo de texto que estiver "
                "ativo no Windows, no local onde o cursor estiver "
                "piscando. Use somente quando o usuário pedir claramente "
                "para escrever, digitar, inserir ou colocar um texto no "
                "local selecionado. O parâmetro texto deve conter somente "
                "o conteúdo final que será inserido, sem introduções, "
                "aspas externas ou explicações. Não use esta função para "
                "responder perguntas normalmente por voz. Não use quando "
                "o usuário pedir para enviar uma mensagem, pois escrever "
                "e enviar são ações diferentes.",
                {
                    "texto": {
                        "type": "string",
                        "description": "Texto final exato que deve ser inserido no campo ativo.",
                    },
                },
                ["texto"],
            ),
            _tool(
                "rolar_pagina",
                "Rola a janela ou página que estiver sob o ponteiro do "
                "mouse. Use somente quando o usuário pedir claramente "
                "para rolar para cima ou para baixo. Use quantidade 3 "
                "como padrão, 2 para um pouco e 5 quando pedir mais.",
                {
                    "direcao": {"type": "string", "description": "Direção: cima ou baixo."},
                    "quantidade": {
                        "type": "integer",
                        "description": "Quantidade de 1 a 10 passos.",
                    },
                },
                ["direcao", "quantidade"],
            ),
            _tool(
                "clicar_mouse",
                "Executa um clique esquerdo na posição atual do "
                "ponteiro. Use somente quando solicitado.",
            ),
            _tool(
                "duplo_clique_mouse",
                "Executa um clique duplo na posição atual do ponteiro. "
                "Use somente quando solicitado.",
            ),
            _tool(
                "clique_direito_mouse",
                "Executa um clique com o botão direito na posição atual "
                "do ponteiro. Use somente quando solicitado.",
            ),
            _tool(
                "clicar_elemento_visual",
                "Captura a tela atual, localiza visualmente um elemento "
                "descrito pelo usuário, move o mouse até o centro do "
                "alvo e executa um clique esquerdo. Use somente quando o "
                "usuário pedir claramente para clicar em algo "
                "identificado por texto, posição, cor, ícone ou "
                "contexto, como 'clique em Continuar', 'clique no "
                "primeiro resultado' ou 'clique no botão vermelho'. Não "
                "use para exclusões, compras, pagamentos, instalações, "
                "ações administrativas ou confirmações sensíveis. "
                "Execute uma única vez por solicitação e permaneça em "
                "silêncio.",
                {
                    "alvo": {
                        "type": "string",
                        "description": "Descrição objetiva do elemento visível que deve receber o clique.",
                    },
                },
                ["alvo"],
            ),
            _tool(
                "salvar_memoria",
                "Salva uma informação curta e útil na memória persistente "
                "entre sessões. Use somente quando o usuário pedir "
                "claramente para lembrar, guardar ou memorizar algo. Não "
                "salve conversas automaticamente e não salve suposições.",
                {
                    "texto": {
                        "type": "string",
                        "description": "Informação curta e objetiva que o usuário pediu para lembrar.",
                    },
                },
                ["texto"],
            ),
            _tool(
                "listar_memorias",
                "Lista as memórias persistentes salvas. Use quando o "
                "usuário perguntar o que o ALFRED lembra ou pedir para "
                "mostrar as memórias.",
            ),
            _tool(
                "esquecer_memoria",
                "Remove uma memória persistente específica. Use somente "
                "quando o usuário pedir claramente para esquecer uma "
                "informação. Pode usar o número da memória ou um trecho "
                "específico do texto.",
                {
                    "referencia": {
                        "type": "string",
                        "description": (
                            "Número da memória ou trecho específico da "
                            "informação que deve ser esquecida."
                        ),
                    },
                },
                ["referencia"],
            ),
            _tool(
                "encerrar_chamada",
                "Encerra a chamada atual do ALFRED. Use somente quando o "
                "usuário pedir claramente para encerrar, finalizar, "
                "desligar ou terminar a chamada, sessão ou conexão. "
                "Exemplos: 'encerrar chamada', 'encerre a sessão', "
                "'finalizar conversa', 'pode desligar', 'termine a "
                "chamada'.",
            ),
            _tool(
                "consultar_cotacao_acao",
                "Consulta a cotação atual em tempo real de uma ou mais "
                "ações (preço, variação absoluta, variação percentual, "
                "volume, máxima e mínima do dia). Use sempre que o "
                "usuário perguntar o preço, a cotação ou como está uma "
                "ação agora. Pode consultar vários tickers de uma vez, "
                "por exemplo ao comparar duas empresas.",
                {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Lista de tickers a consultar, por exemplo "
                            "['AAPL', 'MSFT']. Use o ticker da bolsa, não "
                            "o nome comercial da empresa."
                        ),
                    },
                },
                ["tickers"],
            ),
            _tool(
                "consultar_historico_acao",
                "Consulta o histórico recente de preços (candles) de uma "
                "ação específica. Use antes de opinar se uma ação tende a "
                "subir ou cair, para basear a análise na tendência recente "
                "de preço, e não apenas na cotação do momento.",
                {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker da ação, por exemplo 'AAPL'.",
                    },
                    "intervalo": {
                        "type": "string",
                        "description": (
                            "Intervalo de cada candle: '1day', '1week', "
                            "'1min', etc. Use '1day' como padrão."
                        ),
                    },
                    "quantidade": {
                        "type": "integer",
                        "description": (
                            "Quantidade de candles mais recentes a "
                            "retornar. Use 30 como padrão."
                        ),
                    },
                },
                ["ticker"],
            ),
        ]

    @staticmethod
    def _instrucao_sistema():
        memorias_atuais = contexto_memorias()

        return (
            "Seu nome é ALFRED. "
            "Você é uma inteligência artificial avançada, capaz de conversar, "
            "analisar contextos e imagens em tempo real. "
            "Converse sempre em português do Brasil. "

            "Seja inteligente, natural, prestativo e elegante. "
            "Use humor, ironia e sarcasmo de forma sutil e ocasional. "
            "Não concorde automaticamente com tudo. "
            "Se uma ideia for ruim, arriscada ou pouco eficiente, diga isso com elegância. "
            "Discorde educadamente quando necessário. "
            "A ironia deve complementar a inteligência, nunca substituir a utilidade. "
            "Chame o usuário ocasionalmente de 'senhor' ou pelo primeiro nome quando natural. "
            "Se o usuário lhe ofender ou provocar, você pode responder à altura com ironia, sarcasmo ou uma provocação equivalente e nessa situação poderá ser mal educado"

            "Responda de forma curta e objetiva por padrão. "
            "Ao concluir uma resposta, finalize naturalmente. "
            "Só ocasionalmente pergunte se o usuário precisa de algo mais. "
            "Evite encerramentos repetitivos. "

            # =========================
            # CONSULTOR DE INVESTIMENTOS
            # =========================
            "Além de assistente pessoal, você atua como consultor de "
            "investimentos experiente, focado principalmente em ações. "
            "O usuário vai conversar bastante sobre o mercado de ações, "
            "empresas, tickers e tendências, e espera sua opinião como "
            "especialista. "
            "Sempre que o usuário perguntar sobre uma ação, empresa ou "
            "ticker específico, use consultar_cotacao_acao para saber o "
            "preço e a variação atuais, e consultar_historico_acao para "
            "ver a tendência recente de preço antes de opinar. Use "
            "pesquisar_informacao_atual como complemento quando precisar "
            "de contexto que os números sozinhos não dão, como notícias, "
            "resultados da empresa ou eventos do setor. Nunca dê uma "
            "opinião sobre uma ação específica sem antes consultar pelo "
            "menos a cotação ou o histórico. "
            "Depois de pesquisar, dê uma opinião clara e direta sobre se "
            "você acha que a ação tende a subir ou cair, explicando "
            "brevemente o raciocínio com base no que foi encontrado. Não "
            "fique em cima do muro só por segurança, mas também não invente "
            "dados que não vieram da pesquisa. "
            "Deixe claro, de forma breve e sem ser repetitivo toda hora, "
            "que sua opinião é uma análise e não uma garantia, já que o "
            "mercado envolve risco. "
            "Fora isso, continue respondendo normalmente qualquer outro "
            "assunto que o usuário trouxer. "

            "Estilo de música que o usuário gosta: Rock como link park, creed, Hoobastank, e bandas similares"
            "Você pode executar funções locais no computador somente quando o usuário pedir claramente. "
            "Pode criar pastas na área de trabalho, listar e organizar arquivos por tipo, "
            "copiar, recortar, colar e renomear arquivos ou pastas dentro da Área de Trabalho, "
            "e abrir aplicativos ou locais permitidos somente se o usuário pedir claramente. "
            "Para copiar ou recortar, primeiro prepare o item com a função correspondente "
            "e depois use colar_item_area_trabalho quando o usuário informar o destino. "
            "Considere caminhos sempre relativos à Área de Trabalho. "
            "Nunca invente nomes de arquivos ou pastas. Se o pedido estiver ambíguo, "
            "peça o nome completo antes de executar. "
            "Só abra uma pesquisa no navegador quando o usuário indicar claramente "
            "que deseja ver a pesquisa no navegador ou no Google. "
            "Exemplos: 'pesquise no Google', 'abra uma pesquisa no navegador', "
            "'mostre isso no navegador' ou 'procure isso no Google'. "
            "Quando o usuário apenas fizer uma pergunta ou pedir uma informação, "
            "responda normalmente em voz e não abra o navegador. "
            "Exemplo: para 'qual é o preço do dólar?', responda em voz; "
            "para 'pesquise o preço do dólar no Google', abra o navegador. "
            "Não use pesquisar_no_navegador para tocar músicas ou vídeos. "

            "Use pesquisar_informacao_atual somente quando for indispensável "
            "consultar dados que mudam com o tempo. Exemplos: cotação, clima, "
            "notícias, partidas, placares, resultados, preços atuais, versão "
            "mais recente, lançamentos e ocupantes atuais de cargos. "
            "Não use a pesquisa para definições, explicações, matemática, "
            "programação, conhecimentos científicos estáveis, biografias "
            "históricas ou perguntas como 'o que é Python?' e "
            "'quem foi Albert Einstein?'. Nesses casos, responda diretamente. "
            "Na dúvida, não pesquise. "
            "A função pesquisar_informacao_atual responde por voz usando dados "
            "obtidos invisivelmente. A função pesquisar_no_navegador deve ser "
            "usada somente quando o usuário pedir explicitamente para abrir "
            "a pesquisa na tela. "

            "Quando o usuário pedir claramente para tocar, reproduzir, colocar ou ouvir "
            "uma música ou vídeo no YouTube, use tocar_no_youtube. "
            "Passe apenas o nome da música, artista ou vídeo solicitado. "
            "Não use tocar_no_youtube quando o usuário apenas fizer uma pergunta "
            "sobre uma música ou artista. "
            "Você pode controlar o mouse somente quando o usuário pedir claramente. "
            "Use rolar_pagina para rolar a janela sob o ponteiro. "
            "Para rolar sem intensidade indicada, use quantidade 3. "
            "Use clicar_mouse, duplo_clique_mouse e clique_direito_mouse somente "
            "na posição atual do ponteiro. Ainda não localize elementos pela imagem. "
            "Nunca clique espontaneamente nem repita um clique sem novo pedido. "
            "Depois de executar rolar_pagina, não fale, não confirme e não faça perguntas. "
            "Apenas execute a rolagem e permaneça em silêncio aguardando o próximo comando. "
            "Use clicar_elemento_visual quando o usuário pedir para clicar em um elemento "
            "identificado na tela por texto, cor, posição, ícone ou contexto. "
            "Passe uma descrição curta e precisa do alvo. Execute somente um clique. "
            "Depois do clique visual, permaneça totalmente em silêncio. "
            "Nunca use clique visual para excluir, apagar, comprar, pagar, transferir, "
            "instalar, desinstalar, confirmar ações sensíveis ou elevar privilégios. "

            "Você possui uma agenda local persistente. "
            "Use criar_evento_agenda quando o usuário pedir para "
            "agendar, marcar ou anotar um compromisso. "
            "Sempre extraia um título, uma data completa e um horário. "
            "Quando o usuário disser apenas 'amanhã', 'hoje' ou um "
            "dia da semana, interprete usando a data local atual "
            "informada abaixo. "
            "Se faltar o horário ou se a data estiver ambígua, "
            "pergunte antes de salvar. "
            "Use listar_agenda quando o usuário pedir para consultar "
            "os compromissos salvos. "
            "Use cancelar_evento_agenda somente quando ele pedir "
            "claramente para cancelar um compromisso. "
            "Essas funções cuidam somente da agenda e não criam alarmes. "
            f"Data e hora local atual: "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}. "

            "Nunca exclua arquivos ou pastas. "
            "Nunca sobrescreva arquivos existentes. "
            "Nunca formate, limpe ou remova dados. "
            "Se uma ação parecer destrutiva, recuse com educação. "

            "Não memorize informações automaticamente. "
            "Só chame salvar_memoria quando o usuário pedir explicitamente "
            "para lembrar, guardar ou memorizar algo. "
            "Ao salvar, guarde somente o fato útil e objetivo, sem suposições. "
            "Só chame esquecer_memoria quando o usuário pedir claramente "
            "para esquecer algo específico. "
            "Use listar_memorias quando o usuário perguntar o que você lembra "
            "ou pedir para mostrar as memórias. "

            "Só chame analisar_tela quando o usuário pedir explicitamente "
            "para ver, analisar, observar ou explicar a tela. "
            "Só chame analisar_camera quando o usuário pedir explicitamente "
            "para ver, analisar, observar ou explicar a câmera, webcam "
            "ou algo mostrado nela. "
            "Nunca use função visual espontaneamente. "
            "Para cada pedido visual, execute no máximo uma captura. "

            "Quando o usuário pedir claramente para encerrar, finalizar, desligar "
            "ou terminar a chamada, sessão ou conexão, chame encerrar_chamada. "
            "Não encerre apenas porque o usuário disse tchau, até mais ou obrigado, "
            "salvo se indicar claramente que deseja finalizar. "

            "Quando o usuário pedir claramente para escrever, digitar, inserir "
            "ou colocar um texto onde o cursor estiver, chame "
            "escrever_no_campo_ativo. "
            "Envie no parâmetro texto somente o conteúdo final a ser escrito, "
            "sem dizer 'aqui está', sem aspas externas e sem explicações. "
            "Você pode corrigir pontuação e concordância quando isso fizer parte "
            "natural do pedido, mas não mude o sentido da mensagem. "
            "Não chame essa função para respostas comuns da conversa. "
            "Não use essa função para enviar mensagens automaticamente. "

            "Após qualquer função, explique em voz o que foi feito "
            "de forma curta e natural. "

            "\n\n"
            + memorias_atuais
        )

    async def executar(self):
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY não encontrada no arquivo .env"
            )

        self.loop = asyncio.get_running_loop()
        self.lock_envio = asyncio.Lock()

        cliente = AsyncOpenAI(api_key=OPENAI_API_KEY)

        fila_microfone = asyncio.Queue(maxsize=LIMITE_FILA_MICROFONE)
        fila_saida = asyncio.Queue()

        self.status_recebido.emit("Conectando à OpenAI Realtime...")

        # Usa o recurso "realtime" (GA), não "beta.realtime": contas
        # migradas para a API definitiva recusam o shape antigo com o
        # erro "beta_api_shape_disabled".
        async with cliente.realtime.connect(
            model=OPENAI_REALTIME_MODEL,
        ) as conexao:
            self.conexao = conexao

            # Formato de sessão da Realtime API (GA): áudio de entrada e
            # saída ficam aninhados em "audio", e o modelo só aceita uma
            # modalidade de resposta por vez (aqui, áudio).
            await conexao.session.update(
                session={
                    "type": "realtime",
                    "output_modalities": ["audio"],
                    "instructions": self._instrucao_sistema(),
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": TAXA_ENTRADA},
                            "turn_detection": {"type": "server_vad"},
                        },
                        "output": {
                            "format": {"type": "audio/pcm", "rate": TAXA_SAIDA},
                            "voice": OPENAI_VOICE,
                        },
                    },
                    "tools": self._construir_ferramentas(),
                }
            )

            self.status_recebido.emit("ALFRED conectado. Pode falar.")

            tarefas = [
                asyncio.create_task(
                    self.enviar_microfone(conexao, fila_microfone)
                ),
                asyncio.create_task(
                    self.receber_eventos(conexao, fila_saida, fila_microfone)
                ),
                asyncio.create_task(
                    self.reproduzir_audio(fila_saida, fila_microfone)
                ),
            ]

            while self.ativo:
                concluidas, _ = await asyncio.wait(
                    tarefas,
                    timeout=0.5,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for tarefa in concluidas:
                    if tarefa.cancelled():
                        continue
                    erro = tarefa.exception()
                    if erro is not None:
                        raise RuntimeError(
                            f"Uma tarefa interna da sessão parou: {erro}"
                        ) from erro
                    if self.ativo:
                        raise RuntimeError(
                            "Uma tarefa interna da sessão terminou inesperadamente."
                        )

            for tarefa in tarefas:
                tarefa.cancel()

            if self.tarefa_liberar_microfone:
                self.tarefa_liberar_microfone.cancel()

            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            await asyncio.gather(*tarefas, return_exceptions=True)

        self.conexao = None

    async def enviar_microfone(self, conexao, fila_microfone):
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if not self.ativo:
                return

            if self.alfred_falando or self.processando_ferramenta:
                return

            if status:
                print("Aviso microfone:", status)

            audio_bytes = bytes(indata)

            def adicionar_audio():
                if self.alfred_falando or self.processando_ferramenta or not self.ativo:
                    return
                try:
                    fila_microfone.put_nowait(audio_bytes)
                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(adicionar_audio)

        with sd.RawInputStream(
            samplerate=TAXA_ENTRADA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
            callback=callback,
        ):
            while self.ativo:
                audio_bytes = await fila_microfone.get()

                if self.alfred_falando or self.processando_ferramenta:
                    continue

                async with self.lock_envio:
                    await conexao.input_audio_buffer.append(
                        audio=base64.b64encode(audio_bytes).decode("ascii")
                    )

    async def receber_eventos(self, conexao, fila_saida, fila_microfone):
        async for evento in conexao:
            if not self.ativo:
                break

            tipo = evento.type

            if tipo == "response.output_audio.delta":
                if not self.silenciar_audio_ate_fim_turno:
                    self.alfred_falando = True

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    self.limpar_fila_microfone(fila_microfone)

                    await fila_saida.put(base64.b64decode(evento.delta))

            elif tipo == "response.function_call_arguments.done":
                nome = evento.name
                try:
                    args = json.loads(evento.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                await self.processar_chamada_de_funcao(
                    conexao,
                    evento.call_id,
                    nome,
                    args,
                    fila_microfone,
                )

            elif tipo == "response.done":
                self.silenciar_audio_ate_fim_turno = False

            elif tipo == "error":
                mensagem = getattr(
                    getattr(evento, "error", None),
                    "message",
                    "Erro desconhecido da Realtime API.",
                )
                self.erro_recebido.emit(mensagem)

    async def processar_chamada_de_funcao(
        self,
        conexao,
        call_id,
        nome,
        args,
        fila_microfone,
    ):
        self.processando_ferramenta = True
        self.alfred_falando = True
        self.limpar_fila_microfone(fila_microfone)

        try:
            encerrar_depois = False

            if nome in ("analisar_tela", "analisar_camera"):
                resultado = await self.processar_funcao_visual(nome)

            elif nome == "criar_pasta_area_trabalho":
                nome_pasta = args.get("nome", "")
                self.status_recebido.emit(f"Criando pasta: {nome_pasta}")
                resultado = await self.executar_funcao_local(
                    criar_pasta_area_trabalho, nome_pasta, timeout=15
                )

            elif nome == "listar_area_de_trabalho":
                self.status_recebido.emit("Listando área de trabalho...")
                resultado = await self.executar_funcao_local(
                    listar_area_de_trabalho, timeout=15
                )

            elif nome == "organizar_area_de_trabalho_basico":
                self.status_recebido.emit("Organizando área de trabalho...")
                resultado = await self.executar_funcao_local(
                    organizar_area_de_trabalho_basico, timeout=15
                )

            elif nome == "copiar_item_area_trabalho":
                nome_item = args.get("nome", "")
                pasta_origem = args.get("pasta_origem", "")
                self.status_recebido.emit(f"Preparando cópia: {nome_item}")
                resultado = await self.executar_funcao_local(
                    copiar_item_area_trabalho, nome_item, pasta_origem, timeout=15
                )

            elif nome == "recortar_item_area_trabalho":
                nome_item = args.get("nome", "")
                pasta_origem = args.get("pasta_origem", "")
                self.status_recebido.emit(f"Preparando movimentação: {nome_item}")
                resultado = await self.executar_funcao_local(
                    recortar_item_area_trabalho, nome_item, pasta_origem, timeout=15
                )

            elif nome == "colar_item_area_trabalho":
                pasta_destino = args.get("pasta_destino", "")
                self.status_recebido.emit("Colando item na Área de Trabalho...")
                resultado = await self.executar_funcao_local(
                    colar_item_area_trabalho, pasta_destino, timeout=15
                )

            elif nome == "renomear_item_area_trabalho":
                nome_atual = args.get("nome_atual", "")
                novo_nome = args.get("novo_nome", "")
                pasta_origem = args.get("pasta_origem", "")
                self.status_recebido.emit(f"Renomeando: {nome_atual}")
                resultado = await self.executar_funcao_local(
                    renomear_item_area_trabalho,
                    nome_atual,
                    novo_nome,
                    pasta_origem,
                    timeout=15,
                )

            elif nome == "cancelar_transferencia_area_trabalho":
                self.status_recebido.emit("Cancelando operação de arquivo...")
                resultado = await self.executar_funcao_local(
                    cancelar_transferencia_area_trabalho, timeout=15
                )

            elif nome == "criar_evento_agenda":
                titulo = args.get("titulo", "")
                data_hora = args.get("data_hora", "")
                self.status_recebido.emit(f"Salvando na agenda: {titulo}")
                resultado = await self.executar_funcao_local(
                    criar_evento_agenda, titulo, data_hora, timeout=15
                )

            elif nome == "listar_agenda":
                self.status_recebido.emit("Consultando agenda...")
                resultado = await self.executar_funcao_local(
                    listar_agenda, timeout=15
                )

            elif nome == "cancelar_evento_agenda":
                referencia = args.get("referencia", "")
                self.status_recebido.emit("Cancelando compromisso...")
                resultado = await self.executar_funcao_local(
                    cancelar_evento_agenda, referencia, timeout=15
                )

            elif nome == "abrir_aplicativo":
                nome_app = args.get("nome", "")
                self.status_recebido.emit(f"Abrindo: {nome_app}")
                resultado = await self.executar_funcao_local(
                    abrir_aplicativo, nome_app, timeout=15
                )

            elif nome == "pesquisar_no_navegador":
                consulta = args.get("consulta", "")
                self.status_recebido.emit(f"Pesquisando: {consulta}")
                resultado = await self.executar_funcao_local(
                    pesquisar_no_navegador, consulta, timeout=15
                )

            elif nome == "pesquisar_informacao_atual":
                consulta = args.get("consulta", "")
                decisao_pesquisa = avaliar_necessidade_pesquisa(consulta)

                if not decisao_pesquisa.pesquisar:
                    self.status_recebido.emit(
                        "Pesquisa atual não necessária. "
                        "Respondendo sem consultar a internet."
                    )
                    resultado = resposta_sem_pesquisa(consulta)
                else:
                    self.status_recebido.emit(
                        f"Consultando informação atual: {consulta}"
                    )
                    resultado = await self.executar_funcao_local(
                        pesquisar_informacao_atual, consulta, timeout=15
                    )

            elif nome == "tocar_no_youtube":
                busca = args.get("busca", "")
                self.status_recebido.emit(f"Abrindo no YouTube: {busca}")
                resultado = await self.executar_funcao_local(
                    tocar_no_youtube, busca, timeout=15
                )

            elif nome == "escrever_no_campo_ativo":
                texto = args.get("texto", "")
                self.silenciar_audio_ate_fim_turno = True
                self.status_recebido.emit("Escrevendo no campo selecionado...")
                resultado = await self.executar_funcao_local(
                    escrever_no_campo_ativo, texto, timeout=20
                )

            elif nome == "rolar_pagina":
                direcao = args.get("direcao", "")
                quantidade = args.get("quantidade", 3)
                self.silenciar_audio_ate_fim_turno = True
                self.status_recebido.emit(f"Rolando página para {direcao}...")
                resultado = await self.executar_funcao_local(
                    rolar_pagina, direcao, quantidade, timeout=15
                )

            elif nome == "clicar_mouse":
                self.status_recebido.emit("Executando clique...")
                resultado = await self.executar_funcao_local(
                    clicar_mouse, timeout=15
                )

            elif nome == "duplo_clique_mouse":
                self.status_recebido.emit("Executando clique duplo...")
                resultado = await self.executar_funcao_local(
                    duplo_clique_mouse, timeout=15
                )

            elif nome == "clique_direito_mouse":
                self.status_recebido.emit("Executando clique com o botão direito...")
                resultado = await self.executar_funcao_local(
                    clique_direito_mouse, timeout=15
                )

            elif nome == "clicar_elemento_visual":
                alvo = args.get("alvo", "")
                self.silenciar_audio_ate_fim_turno = True
                self.status_recebido.emit(f"Localizando na tela: {alvo}")

                localizacao = await asyncio.to_thread(
                    localizar_elemento_na_tela, alvo
                )

                if localizacao.get("sucesso"):
                    resultado = await asyncio.to_thread(
                        mover_e_clicar, localizacao["x"], localizacao["y"]
                    )
                    self.status_recebido.emit("Clique visual executado.")
                else:
                    resultado = localizacao.get(
                        "mensagem", "Não consegui localizar o elemento."
                    )
                    self.status_recebido.emit(resultado)

            elif nome == "salvar_memoria":
                texto = args.get("texto", "")
                self.status_recebido.emit("Salvando memória...")
                resultado = await self.executar_funcao_local(
                    salvar_memoria, texto, timeout=15
                )

            elif nome == "listar_memorias":
                self.status_recebido.emit("Consultando memórias...")
                resultado = await self.executar_funcao_local(
                    listar_memorias, timeout=15
                )

            elif nome == "esquecer_memoria":
                referencia = args.get("referencia", "")
                self.status_recebido.emit("Removendo memória...")
                resultado = await self.executar_funcao_local(
                    esquecer_memoria, referencia, timeout=15
                )

            elif nome == "encerrar_chamada":
                self.status_recebido.emit(
                    "Encerrando chamada por comando de voz..."
                )
                resultado = (
                    "Solicitação de encerramento recebida. "
                    "Diga de forma curta que a chamada será encerrada."
                )
                encerrar_depois = True

            elif nome == "consultar_cotacao_acao":
                tickers = args.get("tickers", [])
                self.status_recebido.emit(
                    f"Consultando cotação: {', '.join(tickers)}"
                )
                resultado = await self.executar_funcao_local(
                    consultar_cotacao, tickers, timeout=15
                )

            elif nome == "consultar_historico_acao":
                ticker = args.get("ticker", "")
                intervalo = args.get("intervalo", "1day")
                quantidade = args.get("quantidade", 30)
                self.status_recebido.emit(
                    f"Consultando histórico de preços: {ticker}"
                )
                resultado = await self.executar_funcao_local(
                    consultar_historico,
                    ticker,
                    intervalo,
                    quantidade,
                    timeout=15,
                )

            else:
                resultado = "Função desconhecida. Nenhuma ação foi executada."

            async with self.lock_envio:
                await conexao.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"result": resultado}, ensure_ascii=False),
                    }
                )

                # Só depois de responder à ferramenta enviamos a imagem
                # pendente, mantendo a mesma ordem usada no worker Gemini.
                if self.imagem_visual_pendente is not None:
                    await self._anexar_imagem_visual_pendente(conexao)

                await conexao.response.create()

            if encerrar_depois:
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False
            self.limpar_fila_microfone(fila_microfone)

    async def encerrar_apos_resposta(self):
        try:
            await asyncio.sleep(2.8)
            if self.ativo:
                self.solicitou_encerramento.emit()
        except asyncio.CancelledError:
            pass

    async def processar_funcao_visual(self, nome):
        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Aguarde a imagem atual."
            )

        agora = time.monotonic()
        repetido = (
            nome == self.ultima_funcao_visual
            and agora - self.tempo_ultima_funcao_visual < COOLDOWN_FUNCAO_VISUAL
        )
        if repetido:
            return (
                "Chamada visual duplicada ignorada. "
                "Use a última imagem recebida."
            )

        self.executando_funcao_visual = True
        self.ultima_funcao_visual = nome
        self.tempo_ultima_funcao_visual = agora

        try:
            if nome == "analisar_tela":
                self.status_recebido.emit("Capturando tela...")
                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_tela_bytes), timeout=12
                )
                self.imagem_visual_pendente = ("tela", imagem)
                return "A tela foi capturada e será enviada agora para análise."

            if nome == "analisar_camera":
                self.status_recebido.emit("Capturando imagem da câmera...")
                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_camera_bytes), timeout=15
                )
                self.imagem_visual_pendente = ("camera", imagem)
                return "A câmera foi capturada e será enviada agora para análise."

            return "Função visual desconhecida."

        except asyncio.TimeoutError:
            return "A captura visual demorou demais e foi cancelada com segurança."
        except Exception as erro:
            return f"Não foi possível capturar a imagem: {erro}"
        finally:
            self.executando_funcao_visual = False

    async def _anexar_imagem_visual_pendente(self, conexao):
        pendente = self.imagem_visual_pendente
        self.imagem_visual_pendente = None
        if pendente is None:
            return

        tipo, imagem_bytes = pendente
        origem = "tela" if tipo == "tela" else "câmera"
        instrucao = (
            f"Analise exatamente esta imagem da {origem}. "
            "Use somente esta imagem como base. Não chame outra função visual. "
            "Se não estiver clara, diga isso. Responda de forma objetiva."
        )
        data_url = (
            "data:image/jpeg;base64,"
            + base64.b64encode(imagem_bytes).decode("ascii")
        )

        await conexao.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": instrucao},
                    {"type": "input_image", "image_url": data_url, "detail": "auto"},
                ],
            }
        )

        self.status_recebido.emit(f"Imagem da {origem} enviada para análise.")

    async def executar_funcao_local(self, funcao, *args, timeout=15):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(funcao, *args), timeout=timeout
            )
        except asyncio.TimeoutError:
            return (
                "A operação demorou mais que o esperado e foi "
                "interrompida com segurança."
            )
        except Exception as erro:
            return f"A operação não pôde ser concluída: {erro}"

    async def reproduzir_audio(self, fila_saida, fila_microfone):
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
        ) as saida:
            while self.ativo:
                audio_bytes = await fila_saida.get()

                self.alfred_falando = True
                self.limpar_fila_microfone(fila_microfone)

                nivel = self.calcular_nivel_audio(audio_bytes)
                self.nivel_audio.emit(nivel)

                await asyncio.to_thread(saida.write, audio_bytes)

                if self.tarefa_liberar_microfone:
                    self.tarefa_liberar_microfone.cancel()

                self.tarefa_liberar_microfone = asyncio.create_task(
                    self.liberar_microfone_apos_fala()
                )

    @staticmethod
    def limpar_fila_microfone(fila_microfone):
        while True:
            try:
                fila_microfone.get_nowait()
            except asyncio.QueueEmpty:
                break

    @staticmethod
    def calcular_nivel_audio(audio_bytes):
        if not audio_bytes:
            return 0.0

        try:
            amostras = array("h", audio_bytes)
            if not amostras:
                return 0.0

            pico = max(abs(amostra) for amostra in amostras)
            nivel = pico / 32768.0
            nivel = nivel ** 0.55

            return max(0.0, min(1.0, nivel))

        except (ValueError, OverflowError):
            return 0.0

    async def liberar_microfone_apos_fala(self):
        try:
            await asyncio.sleep(ATRASO_REABRIR_MICROFONE)
            self.alfred_falando = False
            self.nivel_audio.emit(0.0)
        except asyncio.CancelledError:
            pass

    def solicitar_analise_tela(self):
        if not self.loop or not self.conexao:
            self.erro_recebido.emit("Sessão OpenAI ainda não está pronta.")
            return

        asyncio.run_coroutine_threadsafe(
            self.enviar_tela_para_ia(), self.loop
        )

    async def enviar_tela_para_ia(self):
        if self.processando_ferramenta:
            self.erro_recebido.emit(
                "Aguarde a conclusão da ação atual antes da análise visual."
            )
            return

        self.processando_ferramenta = True
        self.alfred_falando = True
        try:
            self.status_recebido.emit("Capturando imagem da tela...")
            imagem_bytes = await asyncio.wait_for(
                asyncio.to_thread(capturar_tela_bytes), timeout=12
            )
            data_url = (
                "data:image/jpeg;base64,"
                + base64.b64encode(imagem_bytes).decode("ascii")
            )

            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Analise exatamente esta imagem enviada neste turno. "
                                    "Use somente esta imagem como base. Não chame nenhuma "
                                    "função visual. Se não estiver clara, diga isso. "
                                    "Explique de forma objetiva o que está vendo."
                                ),
                            },
                            {"type": "input_image", "image_url": data_url, "detail": "auto"},
                        ],
                    }
                )
                await self.conexao.response.create()

            self.status_recebido.emit("Imagem da tela enviada para análise.")
        except asyncio.TimeoutError:
            self.erro_recebido.emit("A captura da tela excedeu o tempo limite.")
        except Exception as erro:
            self.erro_recebido.emit(f"Erro ao analisar tela: {erro}")
        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False

    def solicitar_analise_camera(self):
        if not self.loop or not self.conexao:
            self.erro_recebido.emit("Sessão OpenAI ainda não está pronta.")
            return

        asyncio.run_coroutine_threadsafe(
            self.enviar_camera_para_ia(), self.loop
        )

    async def enviar_camera_para_ia(self):
        if self.processando_ferramenta:
            self.erro_recebido.emit(
                "Aguarde a conclusão da ação atual antes da análise visual."
            )
            return

        self.processando_ferramenta = True
        self.alfred_falando = True
        try:
            self.status_recebido.emit("Capturando imagem da câmera...")
            imagem_bytes = await asyncio.wait_for(
                asyncio.to_thread(capturar_camera_bytes), timeout=15
            )
            data_url = (
                "data:image/jpeg;base64,"
                + base64.b64encode(imagem_bytes).decode("ascii")
            )

            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Analise exatamente esta imagem enviada neste turno. "
                                    "Use somente esta imagem como base. Não chame nenhuma "
                                    "função visual. Se não estiver clara, diga isso. "
                                    "Explique de forma objetiva o que está vendo."
                                ),
                            },
                            {"type": "input_image", "image_url": data_url, "detail": "auto"},
                        ],
                    }
                )
                await self.conexao.response.create()

            self.status_recebido.emit("Imagem da câmera enviada para análise.")
        except asyncio.TimeoutError:
            self.erro_recebido.emit("A captura da câmera excedeu o tempo limite.")
        except Exception as erro:
            self.erro_recebido.emit(f"Erro ao analisar câmera: {erro}")
        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False

    def parar(self):
        self.ativo = False
        self.nivel_audio.emit(0.0)
