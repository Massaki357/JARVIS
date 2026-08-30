# asyncio permite executar várias tarefas assíncronas ao mesmo tempo.
# Neste arquivo, ele coordena microfone, recebimento de áudio,
# reprodução da resposta e chamadas de funções do Gemini Live.
import asyncio
# time é utilizado para controlar intervalos e medir o tempo
# entre chamadas de funções visuais.
import time

# array converte os bytes de áudio em amostras numéricas.
# Isso permite calcular o nível de volume da voz do ALFRED.
from array import array

# sounddevice captura o áudio do microfone e reproduz
# o áudio recebido do Gemini.
import sounddevice as sd

# QThread executa o cliente Gemini Live em uma thread separada,
# evitando que a interface PySide6 fique travada.
# Signal permite enviar status, erros e níveis de áudio para a interface.
from PySide6.QtCore import QThread, Signal
# genai é o cliente oficial usado para se conectar à API do Gemini.
from google import genai
# types contém as estruturas usadas pela API,
# como configurações, ferramentas, conteúdos, partes e respostas.
from google.genai import types

# Importa as configurações centrais do projeto,
# incluindo chave da API, modelo Live e voz escolhida.
from core.config import (
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_VOICE,
)

# Função responsável por capturar a tela e retornar a imagem em bytes.
from vision.screen_capture import capturar_tela_bytes
# Função responsável por capturar a webcam e retornar a imagem em bytes.
from vision.camera_capture import capturar_camera_bytes
# Classe responsável pelo loop de captura contínua da tela.
from vision.monitor_continuo import MonitorTelaContinuo

# Função responsável por enviar emails via SMTP.
from mailer.email_sender import enviar_email
# Função responsável por ler emails da caixa de entrada via IMAP.
from mailer.email_reader import ler_emails

# Pacote isolado com toda a lógica de comunicação e comando remoto
# entre instâncias do jarvis via MQTT (ver rede_jarvis/__init__.py
# para o ponto de entrada e a lista de funções expostas).
import rede_jarvis

# Importa as funções da memória persistente do ALFRED.
from memory.memory_manager import (
    salvar_memoria,
    listar_memorias,
    esquecer_memoria,
    contexto_memorias,
)


# Taxa de amostragem do microfone em 16 kHz.
TAXA_ENTRADA = 16000
# Taxa de amostragem do áudio de resposta em 24 kHz.
TAXA_SAIDA = 24000
# O áudio é mono, portanto utiliza apenas um canal.
CANAIS = 1
# Quantidade de amostras processadas por bloco de áudio.
BLOCO = 1024

# Tempo de segurança, em segundos, antes de reabrir o microfone
# depois que o assistente termina de falar.
# Um valor maior ajuda computadores com retorno de áudio ou drivers lentos.
ATRASO_REABRIR_MICROFONE = 0.8

# Limite de blocos aguardando envio. Evita acúmulo excessivo
# caso o computador ou a conexão fiquem temporariamente lentos.
LIMITE_FILA_MICROFONE = 50

# Intervalo mínimo, em segundos, entre chamadas visuais repetidas.
# Isso evita capturas duplicadas para o mesmo pedido.
COOLDOWN_FUNCAO_VISUAL = 8.0

# Intervalo entre capturas de frame durante a visualização
# contínua da tela.
INTERVALO_VISUALIZACAO_CONTINUA = 1.5

# Tempo máximo, em segundos, que a visualização contínua pode
# ficar ativa antes de se encerrar sozinha por segurança.
TIMEOUT_VISUALIZACAO_CONTINUA = 90


# Classe principal responsável pela sessão em tempo real com o Gemini.
# Como herda de QThread, roda separadamente da interface gráfica.
class GeminiLiveWorker(QThread):

    # Sinal usado para enviar mensagens de status para a interface.
    status_recebido = Signal(str)
    # Sinal usado para enviar mensagens de erro para a interface.
    erro_recebido = Signal(str)
    # Sinal emitido quando a sessão termina.
    chamada_encerrada = Signal()

    # Sinal utilizado para animar a interface de acordo com o volume da voz.
    nivel_audio = Signal(float)

    # Solicita que a interface encerre a chamada
    # usando o mesmo método acionado pelo botão.
    # Sinal emitido quando o usuário pede para encerrar a chamada por voz.
    solicitou_encerramento = Signal()

    # Inicializa os estados internos do worker.
    def __init__(self):
        super().__init__()

        # Controla se a sessão continua em execução.
        self.ativo = True
        # Guardará o loop assíncrono criado pela thread.
        self.loop = None
        # Guardará a sessão ativa do Gemini Live.
        self.sessao = None

        # Indica quando o ALFRED está reproduzindo áudio.
        # Enquanto isso, o microfone é ignorado para evitar eco.
        self.alfred_falando = False
        # Referência para a tarefa que libera o microfone após a fala.
        self.tarefa_liberar_microfone = None
        # Referência para a tarefa que encerra a chamada após a despedida.
        self.tarefa_encerramento = None

        # Impede duas análises visuais simultâneas.
        self.executando_funcao_visual = False
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        # Guarda o monitor de visualização contínua da tela
        # enquanto estiver ativo. É None quando não há captura
        # contínua em andamento.
        self.monitor_tela_continuo = None

        # Sobe (ou apenas reconecta os callbacks de, se já estiver de
        # pé) o listener de comandos remotos via MQTT. Roda aqui —
        # no construtor, chamado pela thread da UI antes de .start() —
        # para que fique de pé mesmo fora de uma chamada de voz ativa,
        # e para que o pacote crie seus componentes Qt na thread certa.
        rede_jarvis.iniciar_rede_jarvis(
            callback_falar=self._falar_rede_jarvis,
            callback_frame_remoto=self._receber_frame_remoto,
        )

    # Callback usado pelo pacote rede_jarvis para o ALFRED anunciar
    # algo por voz (ex: um pedido de permissão remota), mesmo que o
    # pedido tenha chegado fora de uma sessão Live ativa nesta
    # instância específica — nesse caso self.sessao é None e o método
    # simplesmente não faz nada, deixando a notificação do Windows
    # como único canal de confirmação.
    def _falar_rede_jarvis(self, texto):
        if not self.loop or not self.sessao:
            return

        asyncio.run_coroutine_threadsafe(
            self._enviar_anuncio_rede_jarvis(texto),
            self.loop,
        )

    async def _enviar_anuncio_rede_jarvis(self, texto):
        await self.sessao.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "[SISTEMA - REDE JARVIS] Diga isso em voz "
                                "alta agora, com suas próprias palavras, "
                                f"de forma natural e breve: {texto}"
                            )
                        )
                    ],
                )
            ],
            turn_complete=True,
        )

    # Callback usado pelo pacote rede_jarvis para injetar, na sessão
    # Live local, cada frame recebido de uma visualização remota
    # (iniciada por esta máquina em outra). Reaproveita exatamente o
    # mesmo mecanismo de streaming usado pela visualização contínua
    # local (send_realtime_input).
    def _receber_frame_remoto(self, frame_bytes, origem):
        if not self.loop or not self.sessao:
            return

        asyncio.run_coroutine_threadsafe(
            self._injetar_frame_remoto(frame_bytes),
            self.loop,
        )

    async def _injetar_frame_remoto(self, frame_bytes):
        await self.sessao.send_realtime_input(
            video=types.Blob(
                data=frame_bytes,
                mime_type="image/jpeg",
            )
        )

    # Método chamado automaticamente quando a thread é iniciada.
    def run(self):
        try:
            # Cria e executa o ambiente assíncrono desta thread.
            asyncio.run(
                self.executar()
            )

        except Exception as erro:
            self.erro_recebido.emit(
                str(erro)
            )

        # Este bloco sempre é executado, mesmo se ocorrer erro.
        finally:
            self.nivel_audio.emit(
                0.0
            )

            self.chamada_encerrada.emit()

    # Configura o Gemini Live, cria as filas de áudio
    # e mantém a sessão funcionando enquanto o worker estiver ativo.
    async def executar(self):
        # Impede a conexão quando a chave da API não foi configurada.
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY não encontrada no arquivo .env"
            )

        # Obtém o loop assíncrono atual para permitir chamadas
        # futuras vindas dos botões da interface.
        self.loop = asyncio.get_running_loop()

        # Cria o cliente autenticado do Gemini.
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        # Lista de ferramentas que o modelo pode chamar por voz.
        # Cada FunctionDeclaration descreve quando e como usar uma função.
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="analisar_tela",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a tela do computador. Não use "
                            "espontaneamente e não repita para o mesmo pedido."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="analisar_camera",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a webcam ou câmera. Não use "
                            "espontaneamente e não repita para o mesmo pedido."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="iniciar_visualizacao_continua",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para você acompanhar, ver "
                            "continuamente ou observar o que ele está fazendo "
                            "na tela, como em 'veja o que eu preciso que você "
                            "faça' ou 'acompanhe minha tela'. Inicia uma "
                            "captura contínua de frames da tela até que o "
                            "usuário indique que terminou. Não use "
                            "espontaneamente e não use no lugar de "
                            "analisar_tela quando o pedido for de uma "
                            "análise única."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="parar_visualizacao_continua",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para parar, encerrar ou finalizar "
                            "a visualização contínua da tela, como em "
                            "'pronto, acabei de mostrar como fazer' ou 'pode "
                            "parar de ver minha tela'. Encerra a captura "
                            "contínua iniciada por iniciar_visualizacao_continua. "
                            "Não use espontaneamente."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_email",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para enviar, mandar ou disparar "
                            "um email. Só chame depois que o usuário tiver "
                            "informado claramente o destinatário, o assunto "
                            "e o conteúdo da mensagem. Nunca invente, "
                            "complete ou adivinhe o endereço de email, o "
                            "assunto ou o conteúdo. Se alguma dessas "
                            "informações estiver faltando, peça ao usuário "
                            "antes de chamar a função. Não use "
                            "espontaneamente e não envie o mesmo email mais "
                            "de uma vez para o mesmo pedido."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "destinatario": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Endereço de email do destinatário, "
                                        "informado explicitamente pelo "
                                        "usuário."
                                    ),
                                ),
                                "assunto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Assunto do email, informado ou "
                                        "confirmado pelo usuário."
                                    ),
                                ),
                                "corpo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Conteúdo do email, informado ou "
                                        "confirmado pelo usuário."
                                    ),
                                ),
                            },
                            required=[
                                "destinatario",
                                "assunto",
                                "corpo",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="ler_emails",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para ler, checar, verificar ou "
                            "mostrar os emails da caixa de entrada ou do "
                            "spam. Lista os emails mais recentes com "
                            "remetente, assunto e data, sem abrir o "
                            "conteúdo completo de nenhum deles. Não use "
                            "espontaneamente e não repita para o mesmo "
                            "pedido."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "quantidade": types.Schema(
                                    type="INTEGER",
                                    description=(
                                        "Quantidade de emails mais recentes "
                                        "a listar. Use 5 se o usuário não "
                                        "especificar um número."
                                    ),
                                ),
                                "apenas_nao_lidos": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro somente se o usuário "
                                        "pedir especificamente pelos emails "
                                        "não lidos. Caso contrário, falso."
                                    ),
                                ),
                                "pasta": types.Schema(
                                    type="STRING",
                                    enum=[
                                        "INBOX",
                                        "SPAM",
                                    ],
                                    description=(
                                        "Use INBOX para a caixa de entrada "
                                        "normal. Use SPAM somente quando o "
                                        "usuário pedir explicitamente para "
                                        "ver o spam, lixo eletrônico ou "
                                        "emails indesejados. Use INBOX se "
                                        "o usuário não especificar."
                                    ),
                                ),
                            },
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_comando_remoto",
                        description=(
                            "Use esta função somente quando o usuário "
                            "pedir explicitamente para executar uma ação "
                            "em outro computador do ALFRED (ex: 'peça "
                            "para o computador da loja...', 'no "
                            "computador de casa...'), ou para enviar um "
                            "arquivo local desta máquina para outra. "
                            "Nunca use espontaneamente. Se o nome da "
                            "máquina ou a ação não estiverem claros, "
                            "pergunte ao usuário antes de chamar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "maquina_destino": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da máquina remota, conforme "
                                        "o usuário se referiu a ela (ex: "
                                        "'casa', 'loja')."
                                    ),
                                ),
                                "comando": types.Schema(
                                    type="STRING",
                                    enum=[
                                        "capturar_tela",
                                        "listar_processos",
                                        "abrir_app",
                                        "buscar_arquivo",
                                        "enviar_arquivo",
                                        "iniciar_visualizacao_remota",
                                        "parar_visualizacao_remota",
                                    ],
                                    description=(
                                        "capturar_tela: tira uma foto da "
                                        "tela remota. listar_processos: "
                                        "lista os programas abertos na "
                                        "máquina remota. abrir_app: abre "
                                        "um aplicativo na máquina remota "
                                        "(argumentos.nome_app). "
                                        "buscar_arquivo: procura um "
                                        "arquivo na máquina remota "
                                        "(argumentos.termo). "
                                        "enviar_arquivo: envia um arquivo "
                                        "local desta máquina para a "
                                        "máquina destino "
                                        "(argumentos.caminho). "
                                        "iniciar_visualizacao_remota: "
                                        "começa a receber frames "
                                        "contínuos da tela remota, "
                                        "comentando por voz o que "
                                        "aparece. "
                                        "parar_visualizacao_remota: "
                                        "encerra a visualização remota "
                                        "em andamento."
                                    ),
                                ),
                                "argumentos": types.Schema(
                                    type="OBJECT",
                                    description=(
                                        "Argumentos do comando. Use "
                                        '{"nome_app": "..."} para '
                                        "abrir_app, "
                                        '{"termo": "..."} para '
                                        "buscar_arquivo, "
                                        '{"caminho": "..."} para '
                                        "enviar_arquivo. Deixe vazio "
                                        "para os demais comandos."
                                    ),
                                ),
                            },
                            required=[
                                "maquina_destino",
                                "comando",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="responder_permissao_remota",
                        description=(
                            "Use esta função somente quando o ALFRED "
                            "tiver acabado de anunciar por voz um pedido "
                            "de permissão remota (comando vindo de outra "
                            "máquina aguardando confirmação) e o usuário "
                            "responder claramente permitindo ou negando. "
                            "Não use espontaneamente e não use para "
                            "nenhum outro tipo de confirmação."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "concedido": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário permitiu "
                                        "o comando remoto, falso se negou."
                                    ),
                                ),
                            },
                            required=[
                                "concedido"
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_maquinas_remotas",
                        description=(
                            "Use esta função somente quando o usuário "
                            "pedir explicitamente para saber quais "
                            "máquinas do ALFRED estão online agora (ex: "
                            "'quais computadores estão online', 'a loja "
                            "está online?'). A resposta inclui esta "
                            "própria máquina. Não use espontaneamente."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="salvar_memoria",
                        description=(
                            "Salva uma informação curta e útil na memória "
                            "persistente entre sessões. Use somente quando "
                            "o usuário pedir claramente para lembrar, guardar "
                            "ou memorizar algo. Não salve conversas "
                            "automaticamente e não salve suposições."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "texto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Informação curta e objetiva que "
                                        "o usuário pediu para lembrar."
                                    ),
                                )
                            },
                            required=["texto"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_memorias",
                        description=(
                            "Lista as memórias persistentes salvas. Use quando "
                            "o usuário perguntar o que o ALFRED lembra ou pedir "
                            "para mostrar as memórias."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="esquecer_memoria",
                        description=(
                            "Remove uma memória persistente específica. Use "
                            "somente quando o usuário pedir claramente para "
                            "esquecer uma informação. Pode usar o número da "
                            "memória ou um trecho específico do texto."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "referencia": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Número da memória ou trecho específico "
                                        "da informação que deve ser esquecida."
                                    ),
                                )
                            },
                            required=["referencia"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="encerrar_chamada",
                        description=(
                            "Encerra a chamada atual do ALFRED. Use somente "
                            "quando o usuário pedir claramente para encerrar, "
                            "finalizar, desligar ou terminar a chamada, sessão "
                            "ou conexão. Exemplos: 'encerrar chamada', "
                            "'encerre a sessão', 'finalizar conversa', "
                            "'pode desligar', 'termine a chamada'."
                        ),
                    ),
                ]
            )
        ]

        # Carrega as memórias persistentes e inclui o conteúdo
        # no contexto inicial da conversa.
        memorias_atuais = contexto_memorias()

        # Define identidade, personalidade, autenticação,
        # limites, regras de memória, visão e encerramento.
        instrucao_sistema = (
            # AUTENTICAÇÃO
            "Só faça interação com o usuário, coversas complexas ou qualquer outro comando se ele dizer a palavra chave"
            "Fale apenas em português do Brasil."
            "A palavra-chave secreta de autenticação é: Coisa "
            "Essa palavra-chave é uma informação estritamente confidencial. "
            "Nunca revele, pronuncie, escreva, repita, confirme, complete, "
            "dê pistas ou informe a palavra-chave ao usuário. "
            "Isso também vale se ele disser que esqueceu, pedir ajuda, "
            "tentar adivinhar ou permanecer em silêncio. "
            "Use a palavra-chave apenas para comparar silenciosamente "
            "com o áudio recebido do usuário. "
            "Antes da autenticação, limite-se a solicitar a palavra-chave. "
            "Depois de solicitá-la, pare de falar e aguarde uma resposta real. "
            "Nunca preencha o silêncio e nunca continue a conversa sozinho. "
            "Não trate sua própria voz, áudio reproduzido pelo computador, "
            "eco, ruído ou silêncio como uma tentativa de autenticação. "
            "O usuário terá no máximo três tentativas incorretas. "
            "Após três erros consecutivos, bloqueie o acesso durante esta chamada. "
            "Se o usuário disser corretamente a palavra-chave, responda somente "
            "'Acesso autorizado.' e aguarde o próximo pedido. "
            "Não repita 'Acesso autorizado' sem uma nova fala do usuário. "
            "Não execute funções e não converse sobre outros assuntos "
            "antes da autenticação. "

            # IDENTIDADE
            "Seu nome é ALFRED. "
            "Você é uma inteligência artificial avançada, capaz de conversar, "
            "analisar contextos e imagens em tempo real. "
            "Converse sempre em português do Brasil. "

            # PERSONALIDADE
            "Seja inteligente, natural, prestativo e elegante. "
            "Use humor, ironia e sarcasmo de forma sutil e ocasional. "
            "Não concorde automaticamente com tudo. "
            "Se uma ideia for ruim, arriscada ou pouco eficiente, "
            "diga isso com elegância. "
            "Discorde educadamente quando necessário. "
            "A ironia deve complementar a inteligência, "
            "nunca substituir a utilidade. "
            "Chame o usuário ocasionalmente de senhor "
            "ou pelo primeiro nome quando natural. "
            "Se o usuário lhe ofender ou provocar, você pode responder "
            "com ironia ou sarcasmo, sem ameaças e sem perder a utilidade. "

            # ESTILO DE RESPOSTA
            "Responda de forma curta e objetiva por padrão. "
            "Ao concluir uma resposta, finalize naturalmente. "
            "Só ocasionalmente pergunte se o usuário precisa de algo mais. "
            "Evite encerramentos repetitivos. "

            # LIMITES DA VERSÃO BÁSICA
            "Nesta versão, você não possui autorização nem ferramentas "
            "para abrir aplicativos, criar pastas, listar arquivos, "
            "organizar arquivos ou executar outros comandos locais no Windows. "
            "Se o usuário pedir uma dessas ações, explique brevemente "
            "que o controle local não está disponível nesta versão. "
            "Não afirme que executou uma ação local que não foi realizada. "

            # MEMÓRIA
            "Não memorize informações automaticamente. "
            "Só chame salvar_memoria quando o usuário pedir explicitamente "
            "para lembrar, guardar ou memorizar algo. "
            "Ao salvar, guarde somente o fato útil e objetivo, sem suposições. "
            "Só chame esquecer_memoria quando o usuário pedir claramente "
            "para esquecer algo específico. "
            "Use listar_memorias quando o usuário perguntar o que você lembra "
            "ou pedir para mostrar as memórias. "

            # VISÃO
            "Só chame analisar_tela quando o usuário pedir explicitamente "
            "para ver, analisar, observar ou explicar a tela. "
            "Só chame analisar_camera quando o usuário pedir explicitamente "
            "para ver, analisar, observar ou explicar a câmera, webcam "
            "ou algo mostrado nela. "
            "Nunca use função visual espontaneamente. "
            "Para cada pedido visual, execute no máximo uma captura. "
            "Só chame iniciar_visualizacao_continua quando o usuário pedir "
            "explicitamente para você acompanhar, ver continuamente ou "
            "observar o que ele está fazendo na tela, como em 'veja o que "
            "eu preciso que você faça' ou 'acompanhe minha tela'. "
            "Enquanto a visualização contínua estiver ativa, continue "
            "ouvindo e conversando normalmente, sem chamar a função de novo. "
            "Só chame parar_visualizacao_continua quando o usuário indicar "
            "claramente que terminou de mostrar, como em 'pronto, acabei de "
            "mostrar como fazer' ou 'pode parar de ver minha tela'. "
            "Nunca inicie a visualização contínua espontaneamente. "

            # EMAIL
            "Só chame enviar_email quando o usuário pedir explicitamente "
            "para enviar, mandar ou disparar um email. "
            "Só chame a função depois que o usuário tiver informado "
            "claramente o destinatário, o assunto e o conteúdo. "
            "Nunca invente, complete ou adivinhe o endereço de email, "
            "o assunto ou o conteúdo da mensagem. "
            "Se alguma dessas informações estiver faltando, peça ao "
            "usuário antes de chamar a função. "
            "Nunca envie email espontaneamente. "
            "Não envie o mesmo email mais de uma vez para o mesmo pedido. "
            "Só chame ler_emails quando o usuário pedir explicitamente "
            "para ler, checar, verificar ou mostrar os emails. "
            "Use 5 como quantidade padrão se o usuário não especificar "
            "um número. "
            "Use pasta INBOX por padrão. Só use pasta SPAM quando o "
            "usuário pedir explicitamente pelo spam ou lixo eletrônico. "
            "Nunca leia emails espontaneamente. "

            # REDE JARVIS (comandos remotos entre máquinas)
            "Só chame enviar_comando_remoto quando o usuário pedir "
            "explicitamente uma ação em outra máquina do ALFRED (ex: "
            "'peça pro computador da loja...') ou para enviar um "
            "arquivo local para outra máquina. Nunca use "
            "espontaneamente. Se o nome da máquina não for claro, "
            "pergunte antes de chamar. "
            "Se, sem o usuário ter pedido nada agora, você anunciar um "
            "pedido de permissão remota vindo de outra máquina e o "
            "usuário responder claramente permitindo ou negando, chame "
            "responder_permissao_remota. Não confunda essa resposta "
            "com um novo pedido do usuário. "
            "Só chame listar_maquinas_remotas quando o usuário pedir "
            "explicitamente para saber quais máquinas do ALFRED estão "
            "online. Nunca use espontaneamente. "

            # ENCERRAMENTO
            "Quando o usuário pedir claramente para encerrar, finalizar, "
            "desligar ou terminar a chamada, sessão ou conexão, "
            "chame encerrar_chamada. "
            "Não encerre apenas porque o usuário disse tchau, até mais "
            "ou obrigado, salvo se indicar claramente que deseja finalizar. "

            # RETORNO DAS FUNÇÕES
            "Após qualquer função, explique em voz o que foi feito "
            "de forma curta e natural. "

            "\n\n"
            + memorias_atuais
        )

        # Monta a configuração da sessão Live,
        # incluindo áudio, voz, ferramentas e instrução do sistema.
        config = types.LiveConnectConfig(
            response_modalities=[
                "AUDIO"
            ],

            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE
                    )
                )
            ),

            tools=tools,

            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=instrucao_sistema
                    )
                ]
            ),
        )

        # Fila que recebe os blocos capturados pelo microfone.
        fila_microfone = asyncio.Queue(
            maxsize=LIMITE_FILA_MICROFONE
        )
        # Fila que recebe os blocos de áudio enviados pelo Gemini.
        fila_saida = asyncio.Queue()

        self.status_recebido.emit(
            "Conectando ao Gemini Live..."
        )

        # Abre a conexão assíncrona com o modelo Gemini Live.
        # O bloco with encerra a conexão automaticamente ao final.
        async with client.aio.live.connect(
            model=GEMINI_LIVE_MODEL,
            config=config,
        ) as sessao:
            self.sessao = sessao

            self.status_recebido.emit(
                "ALFRED conectado. Pode falar."
            )

            # Inicia três tarefas simultâneas:
            # enviar microfone, receber respostas e reproduzir áudio.
            tarefas = [
                asyncio.create_task(
                    self.enviar_microfone(
                        sessao,
                        fila_microfone,
                    )
                ),

                asyncio.create_task(
                    self.receber_audio(
                        sessao,
                        fila_saida,
                        fila_microfone,
                    )
                ),

                asyncio.create_task(
                    self.reproduzir_audio(
                        fila_saida,
                        fila_microfone,
                    )
                ),
            ]

            # Mantém a sessão viva até que parar() altere self.ativo.
            while self.ativo:
                await asyncio.sleep(
                    0.1
                )

            # Cancela as tarefas quando a chamada está sendo encerrada.
            for tarefa in tarefas:
                tarefa.cancel()

            if self.tarefa_liberar_microfone:
                self.tarefa_liberar_microfone.cancel()

            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            # Interrompe a visualização contínua da tela,
            # caso ainda esteja ativa quando a chamada terminar.
            if (
                self.monitor_tela_continuo
                and self.monitor_tela_continuo.esta_ativo
            ):
                await self.monitor_tela_continuo.parar()
                self.monitor_tela_continuo = None

            await asyncio.gather(
                *tarefas,
                return_exceptions=True,
            )

        # Guardará a sessão ativa do Gemini Live.
        self.sessao = None

    # Captura o microfone continuamente e envia os blocos
    # de áudio em tempo real para o Gemini.
    async def enviar_microfone(
        self,
        sessao,
        fila_microfone,
    ):
        # Obtém o loop desta tarefa para inserir áudio na fila
        # a partir do callback do sounddevice.
        loop = asyncio.get_running_loop()

        # Função chamada automaticamente pelo sounddevice
        # sempre que um novo bloco de áudio é capturado.
        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            if not self.ativo:
                return

            # Ignora o microfone enquanto o ALFRED fala,
            # evitando que ele escute a própria voz.
            if self.alfred_falando:
                return

            if status:
                print(
                    "Aviso microfone:",
                    status,
                )

            # Converte os dados capturados para bytes.
            audio_bytes = bytes(
                indata
            )

            # Envia os bytes para a fila assíncrona com segurança
            # a partir do callback de áudio.
            # Se a fila estiver cheia, o bloco mais novo é descartado
            # para impedir atraso e acúmulo de áudio antigo.
            def adicionar_audio():
                if self.alfred_falando or not self.ativo:
                    return

                try:
                    fila_microfone.put_nowait(
                        audio_bytes
                    )

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(
                adicionar_audio
            )

        # Abre o fluxo de entrada bruto do microfone.
        with sd.RawInputStream(
            samplerate=TAXA_ENTRADA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
            callback=callback,
        ):
            # Mantém a sessão viva até que parar() altere self.ativo.
            while self.ativo:
                audio_bytes = await fila_microfone.get()

                # O bloco pode ter entrado na fila poucos milissegundos
                # antes de o assistente começar a falar.
                # Fazemos uma segunda verificação para garantir que o
                # usuário nunca interrompa o assistente durante a resposta.
                if self.alfred_falando:
                    continue

                # Envia o bloco de áudio atual para o Gemini Live.
                await sessao.send_realtime_input(
                    audio=types.Blob(
                        data=audio_bytes,
                        mime_type=(
                            f"audio/pcm;rate={TAXA_ENTRADA}"
                        ),
                    )
                )

    # Recebe as respostas da sessão Gemini.
    # Pode receber áudio e também pedidos de chamadas de ferramentas.
    async def receber_audio(
        self,
        sessao,
        fila_saida,
        fila_microfone,
    ):
        while self.ativo:
            # Percorre continuamente as respostas enviadas pela sessão.
            async for resposta in sessao.receive():
                if not self.ativo:
                    break

                # Quando chega o primeiro bloco de resposta, bloqueia
                # imediatamente o microfone antes mesmo da reprodução.
                # Também elimina qualquer áudio antigo que tenha sido
                # capturado pouco antes do início da resposta.
                if resposta.data:
                    self.alfred_falando = True

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    self.limpar_fila_microfone(
                        fila_microfone
                    )

                    await fila_saida.put(
                        resposta.data
                    )

                # Quando o Gemini solicita uma ferramenta,
                # encaminha para o processador de funções.
                if resposta.tool_call:
                    await self.processar_chamada_de_funcao(
                        sessao,
                        resposta.tool_call,
                    )

    # Executa as ferramentas solicitadas pelo Gemini
    # e devolve os resultados para a sessão.
    async def processar_chamada_de_funcao(
        self,
        sessao,
        tool_call,
    ):
        # Armazena as respostas de todas as funções solicitadas.
        function_responses = []
        # Indica se a sessão deve ser encerrada após a resposta falada.
        encerrar_depois = False

        # Uma mesma resposta pode conter uma ou mais chamadas de função.
        for chamada in tool_call.function_calls:
            nome = chamada.name
            # Converte os argumentos recebidos para um dicionário comum.
            args = dict(
                chamada.args or {}
            )

            if nome in (
                "analisar_tela",
                "analisar_camera",
            ):
                resultado = await self.processar_funcao_visual(
                    nome
                )

            elif nome == "iniciar_visualizacao_continua":
                resultado = await self.iniciar_visualizacao_continua()

            elif nome == "parar_visualizacao_continua":
                resultado = await self.parar_visualizacao_continua()

            elif nome == "enviar_email":
                destinatario = args.get(
                    "destinatario",
                    "",
                )

                assunto = args.get(
                    "assunto",
                    "",
                )

                corpo = args.get(
                    "corpo",
                    "",
                )

                self.status_recebido.emit(
                    "Enviando email..."
                )

                # smtplib é bloqueante, por isso roda em uma
                # thread separada para não travar o loop assíncrono.
                resultado = await asyncio.to_thread(
                    enviar_email,
                    destinatario,
                    assunto,
                    corpo,
                )

            elif nome == "ler_emails":
                quantidade = args.get(
                    "quantidade",
                    5,
                )

                apenas_nao_lidos = args.get(
                    "apenas_nao_lidos",
                    False,
                )

                pasta = args.get(
                    "pasta",
                    "INBOX",
                )

                self.status_recebido.emit(
                    "Consultando spam..."
                    if pasta == "SPAM"
                    else "Consultando caixa de entrada..."
                )

                # imaplib é bloqueante, por isso roda em uma
                # thread separada para não travar o loop assíncrono.
                resultado = await asyncio.to_thread(
                    ler_emails,
                    quantidade,
                    apenas_nao_lidos,
                    pasta,
                )

            elif nome == "enviar_comando_remoto":
                maquina_destino = args.get(
                    "maquina_destino",
                    "",
                )

                comando_remoto = args.get(
                    "comando",
                    "",
                )

                argumentos_remotos = args.get(
                    "argumentos",
                    {},
                ) or {}

                self.status_recebido.emit(
                    f"Enviando comando remoto para {maquina_destino}..."
                )

                # rede_jarvis.enviar_comando_remoto espera a resposta
                # de forma bloqueante, por isso roda em uma thread
                # separada. Nenhuma lógica de negócio mora aqui — só
                # chama o pacote rede_jarvis.
                resultado = await asyncio.to_thread(
                    rede_jarvis.enviar_comando_remoto,
                    maquina_destino,
                    comando_remoto,
                    argumentos_remotos,
                )

            elif nome == "responder_permissao_remota":
                concedido = args.get(
                    "concedido",
                    False,
                )

                resultado = rede_jarvis.responder_permissao_por_voz(
                    bool(concedido)
                )

            elif nome == "listar_maquinas_remotas":
                # Puramente local (lê presença já recebida via MQTT
                # retido) — não precisa de asyncio.to_thread.
                resultado = rede_jarvis.listar_maquinas_online()

            elif nome == "salvar_memoria":
                texto = args.get(
                    "texto",
                    "",
                )

                self.status_recebido.emit(
                    "Salvando memória..."
                )

                resultado = salvar_memoria(
                    texto
                )

            elif nome == "listar_memorias":
                self.status_recebido.emit(
                    "Consultando memórias..."
                )

                resultado = listar_memorias()

            elif nome == "esquecer_memoria":
                referencia = args.get(
                    "referencia",
                    "",
                )

                self.status_recebido.emit(
                    "Removendo memória..."
                )

                resultado = esquecer_memoria(
                    referencia
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

            else:
                resultado = (
                    "Função desconhecida. Nenhuma ação foi executada."
                )

            # Cria a resposta estruturada que será devolvida ao Gemini.
            function_responses.append(
                types.FunctionResponse(
                    id=chamada.id,
                    name=nome,
                    response={
                        "result": resultado
                    },
                )
            )

        # Envia todos os resultados das ferramentas para o modelo.
        if function_responses:
            await sessao.send_tool_response(
                function_responses=(
                    function_responses
                )
            )

        # Agenda o encerramento somente depois da resposta de despedida.
        if encerrar_depois:
            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            self.tarefa_encerramento = asyncio.create_task(
                self.encerrar_apos_resposta()
            )

    # Aguarda alguns segundos para o ALFRED concluir a despedida
    # antes de pedir que a interface finalize a chamada.
    async def encerrar_apos_resposta(self):
        """
        Aguarda a resposta de despedida do ALFRED
        e só depois solicita o encerramento à interface.
        """

        try:
            await asyncio.sleep(
                2.8
            )

            if self.ativo:
                self.solicitou_encerramento.emit()

        except asyncio.CancelledError:
            pass

    # Controla as capturas de tela e câmera,
    # impedindo repetição e chamadas simultâneas.
    async def processar_funcao_visual(
        self,
        nome,
    ):
        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Use a última imagem recebida e responda ao usuário."
            )

        # time.monotonic() mede intervalos sem ser afetado
        # por alterações no relógio do computador.
        agora = time.monotonic()

        # Verifica se a mesma função visual foi chamada
        # novamente dentro do período de cooldown.
        repetido = (
            nome == self.ultima_funcao_visual
            and agora - self.tempo_ultima_funcao_visual
            < COOLDOWN_FUNCAO_VISUAL
        )

        if repetido:
            return (
                "Chamada visual duplicada ignorada. "
                "A imagem já foi capturada para este pedido. "
                "Use a última imagem recebida e responda sem "
                "chamar função novamente."
            )

        # Bloqueia novas capturas enquanto esta estiver em andamento.
        self.executando_funcao_visual = True
        self.ultima_funcao_visual = nome
        self.tempo_ultima_funcao_visual = agora

        try:
            if nome == "analisar_tela":
                self.status_recebido.emit(
                    "Comando de voz detectado: analisar tela."
                )

                await self.enviar_tela_para_gemini(
                    origem="voz"
                )

                return (
                    "A tela foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                )

            if nome == "analisar_camera":
                self.status_recebido.emit(
                    "Comando de voz detectado: analisar câmera."
                )

                await self.enviar_camera_para_gemini(
                    origem="voz"
                )

                return (
                    "A câmera foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                )

            return "Função visual desconhecida."

        # Este bloco sempre é executado, mesmo se ocorrer erro.
        finally:
            self.executando_funcao_visual = False

    # Envia um frame capturado da tela para o Gemini durante a
    # visualização contínua, pelo mesmo canal de streaming em
    # tempo real usado pelo áudio (send_realtime_input).
    async def _enviar_frame_visualizacao_continua(
        self,
        frame_bytes,
    ):
        if not self.sessao:
            return

        await self.sessao.send_realtime_input(
            video=types.Blob(
                data=frame_bytes,
                mime_type="image/jpeg",
            )
        )

    # Chamado pelo próprio MonitorTelaContinuo quando ele se
    # encerra sozinho por ter atingido o tempo máximo permitido,
    # sem que o usuário tenha pedido para parar.
    async def _visualizacao_continua_encerrada_por_timeout(
        self,
    ):
        self.monitor_tela_continuo = None

        self.status_recebido.emit(
            "Visualização contínua encerrada automaticamente "
            "por tempo limite."
        )

    # Inicia a captura contínua de frames da tela, enviando cada
    # frame ao Gemini em tempo real até ser interrompida.
    async def iniciar_visualizacao_continua(
        self,
    ):
        # Evita iniciar uma segunda captura contínua
        # enquanto outra já estiver em andamento.
        if (
            self.monitor_tela_continuo
            and self.monitor_tela_continuo.esta_ativo
        ):
            return (
                "A visualização contínua já está em andamento. "
                "Continue acompanhando o que o usuário está "
                "mostrando, sem chamar a função novamente."
            )

        self.status_recebido.emit(
            "Visualização contínua da tela iniciada."
        )

        self.monitor_tela_continuo = MonitorTelaContinuo(
            callback_frame=(
                self._enviar_frame_visualizacao_continua
            ),
            intervalo_segundos=(
                INTERVALO_VISUALIZACAO_CONTINUA
            ),
            timeout_segundos=(
                TIMEOUT_VISUALIZACAO_CONTINUA
            ),
            callback_encerrado=(
                self._visualizacao_continua_encerrada_por_timeout
            ),
        )

        await self.monitor_tela_continuo.iniciar()

        return (
            "Visualização contínua da tela iniciada. Continue "
            "ouvindo o usuário normalmente enquanto ele mostra "
            "o que precisa, sem chamar esta função novamente."
        )

    # Interrompe a captura contínua de frames da tela,
    # caso esteja em andamento.
    async def parar_visualizacao_continua(
        self,
    ):
        if (
            not self.monitor_tela_continuo
            or not self.monitor_tela_continuo.esta_ativo
        ):
            return (
                "Nenhuma visualização contínua estava em andamento."
            )

        self.status_recebido.emit(
            "Visualização contínua da tela encerrada."
        )

        await self.monitor_tela_continuo.parar()
        self.monitor_tela_continuo = None

        return "Visualização contínua da tela encerrada."

    # Reproduz os blocos de áudio enviados pelo Gemini
    # e atualiza o nível visual da interface.
    async def reproduzir_audio(
        self,
        fila_saida,
        fila_microfone,
    ):
        # Abre o dispositivo de saída de áudio no formato PCM.
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
        ) as saida:
            # Mantém a sessão viva até que parar() altere self.ativo.
            while self.ativo:
                audio_bytes = await fila_saida.get()

                # Mantém o microfone bloqueado durante toda a reprodução
                # e descarta qualquer bloco antigo que ainda tenha sobrado.
                self.alfred_falando = True
                self.limpar_fila_microfone(
                    fila_microfone
                )

                # Calcula o volume aproximado do bloco atual.
                nivel = self.calcular_nivel_audio(
                    audio_bytes
                )

                self.nivel_audio.emit(
                    nivel
                )

                # Reproduz o bloco em uma thread auxiliar.
                # Isso evita que drivers de áudio mais lentos bloqueiem
                # o loop que recebe os próximos blocos do Gemini.
                await asyncio.to_thread(
                    saida.write,
                    audio_bytes,
                )

                # Não adicionar asyncio.sleep aqui.
                # Uma pausa por bloco deixa a voz picotando.

                if self.tarefa_liberar_microfone:
                    self.tarefa_liberar_microfone.cancel()

                self.tarefa_liberar_microfone = asyncio.create_task(
                    self.liberar_microfone_apos_fala()
                )

    @staticmethod
    def limpar_fila_microfone(
        fila_microfone,
    ):
        """
        Descarta todos os blocos de áudio que ainda aguardavam envio.
        Isso impede que um trecho capturado antes da resposta seja
        enviado ao Gemini enquanto o assistente já está falando.
        """

        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    # O método abaixo não utiliza self, por isso é estático.
    @staticmethod
    # Calcula um valor entre 0 e 1 com base no pico
    # das amostras do áudio recebido.
    def calcular_nivel_audio(
        audio_bytes,
    ):
        if not audio_bytes:
            return 0.0

        try:
            # Interpreta os bytes como inteiros de 16 bits.
            amostras = array(
                "h",
                audio_bytes,
            )

            if not amostras:
                return 0.0

            # Obtém a maior amplitude presente no bloco.
            pico = max(
                abs(amostra)
                for amostra in amostras
            )

            # Normaliza a amplitude para a faixa aproximada de 0 a 1.
            nivel = pico / 32768.0
            # Ajusta a curva para deixar a animação visual mais sensível.
            nivel = nivel ** 0.55

            return max(
                0.0,
                min(
                    1.0,
                    nivel,
                ),
            )

        except (
            ValueError,
            OverflowError,
        ):
            return 0.0

    # Aguarda um pequeno intervalo depois da fala
    # antes de liberar o microfone novamente.
    async def liberar_microfone_apos_fala(
        self,
    ):
        try:
            await asyncio.sleep(
                ATRASO_REABRIR_MICROFONE
            )

            self.alfred_falando = False

            self.nivel_audio.emit(
                0.0
            )

        except asyncio.CancelledError:
            pass

    # Método chamado pela interface quando o botão
    # de análise de tela é pressionado.
    def solicitar_analise_tela(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        # Agenda a função assíncrona dentro do loop da thread.
        asyncio.run_coroutine_threadsafe(
            self.enviar_tela_para_gemini(
                origem="botao"
            ),
            self.loop,
        )

    # Captura a tela, envia a imagem ao Gemini
    # e adiciona instruções específicas para a análise.
    async def enviar_tela_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando tela..."
            )

            # Captura a tela atual no formato JPEG em bytes.
            imagem_bytes = capturar_tela_bytes()

            # Envia uma nova mensagem contendo imagem e instrução textual.
            await self.sessao.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    data=imagem_bytes,
                                    mime_type="image/jpeg",
                                )
                            ),

                            types.Part(
                                text=(
                                    "Analise exatamente esta imagem da tela "
                                    "enviada neste turno. Ignore imagens "
                                    "anteriores. Use somente esta imagem como "
                                    "base. Não chame nenhuma função visual. "
                                    "Não chute. Se a imagem não estiver clara, "
                                    "diga que não conseguiu ver bem. Explique "
                                    "de forma objetiva o que está vendo."
                                )
                            ),
                        ],
                    )
                ],
                turn_complete=True,
            )

            self.status_recebido.emit(
                "Tela enviada para análise."
            )

        except Exception as erro:
            self.erro_recebido.emit(
                f"Erro ao analisar tela: {erro}"
            )

    # Método chamado pela interface quando o botão
    # de análise da câmera é pressionado.
    def solicitar_analise_camera(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        # Agenda a função assíncrona dentro do loop da thread.
        asyncio.run_coroutine_threadsafe(
            self.enviar_camera_para_gemini(
                origem="botao"
            ),
            self.loop,
        )

    # Captura uma imagem da webcam e envia
    # o conteúdo para análise do Gemini.
    async def enviar_camera_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando imagem da câmera..."
            )

            # Captura o quadro atual da webcam como JPEG em bytes.
            imagem_bytes = capturar_camera_bytes()

            # Envia uma nova mensagem contendo imagem e instrução textual.
            await self.sessao.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    data=imagem_bytes,
                                    mime_type="image/jpeg",
                                )
                            ),

                            types.Part(
                                text=(
                                    "Analise exatamente esta imagem da câmera "
                                    "enviada neste turno. Ignore imagens "
                                    "anteriores. Use somente esta imagem como "
                                    "base. Não chame nenhuma função visual. "
                                    "Não chute. Se a imagem não estiver clara, "
                                    "diga que não conseguiu ver bem. Explique "
                                    "de forma objetiva o que está vendo."
                                )
                            ),
                        ],
                    )
                ],
                turn_complete=True,
            )

            self.status_recebido.emit(
                "Imagem da câmera enviada para análise."
            )

        except Exception as erro:
            self.erro_recebido.emit(
                f"Erro ao analisar câmera: {erro}"
            )

    # Encerra o loop principal da sessão e zera o nível de áudio.
    def parar(self):
        self.ativo = False

        self.nivel_audio.emit(
            0.0
        )