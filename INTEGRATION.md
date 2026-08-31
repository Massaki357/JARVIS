# Integração dos pacotes de tools com o cliente Gemini Live

Este arquivo é a fonte da verdade de como religar os pacotes isolados
(`rede_jarvis/`, `casa_inteligente/`, `delegacao_ia/`, `admin_terminal/`,
`configuracoes/`, `identificacao_planta/`, `identificacao_visual/`,
`explorador_windows/`, `chat_jarvis/`, `abrir_app_local/`, e outros que vierem
depois) a QUALQUER arquivo cliente Gemini Live — seja o `gemini/live_client_basic.py`
atual (temporário, será substituído quando a versão completa do curso chegar) ou o
arquivo cliente da versão final.

**Atualize este arquivo toda vez que um pacote novo for criado, ou que
a forma de religar um pacote existente mudar.**

## Por que esse padrão existe

Os arquivos com sufixo `_basic` (`main_basic.py`, `live_client_basic.py`,
`main_window_basic.py`) são temporários. Nenhuma lógica importante pode
depender de edições feitas diretamente neles — a integração precisa ser
fácil de "religar" em outro arquivo cliente no futuro, sem precisar
reimplementar nada.

## O contrato: duas funções por pacote

Todo pacote de tools isolado (`rede_jarvis`, `casa_inteligente`,
`delegacao_ia`, `admin_terminal`, `identificacao_planta`, `identificacao_visual`, ...)
expõe exatamente duas funções no seu `__init__.py`:

### `obter_function_declarations() -> list[types.FunctionDeclaration]`
Retorna a lista de `types.FunctionDeclaration` desse pacote, prontas
para entrar na lista `tools` do Gemini Live. O cliente nunca precisa
conhecer os nomes das tools individuais de um pacote — só chama essa
função e estende a lista nativa com o resultado.

### `despachar(nome_funcao, argumentos) -> str | None`
Se `nome_funcao` for reconhecido por esse pacote, executa a ação e
retorna o resultado (sempre uma string, pronta para o Jarvis falar).
Se não for reconhecido, retorna `None` — o chamador tenta o próximo
pacote da lista, ou trata como tool nativa/não encontrada.

`despachar()` é **síncrona e pode bloquear** (chamadas de rede, I/O de
disco, etc.) — quem chama é responsável por rodar isso fora do event
loop (`asyncio.to_thread`), igual o trecho abaixo já faz. Um pacote
nunca precisa saber que está sendo chamado de dentro de uma sessão
assíncrona do Gemini.

## Trecho pronto para copiar

Isto é tudo que um arquivo cliente Gemini Live precisa conter para usar
os pacotes existentes. Adicionar um pacote novo no futuro é só repetir
o padrão: importar e incluir em `PACOTES_REGISTRADOS` — nenhuma outra
linha deste arquivo muda.

```python
# 1. Imports (topo do arquivo, junto dos demais imports do projeto)
import rede_jarvis
import casa_inteligente
import delegacao_ia
import admin_terminal
import configuracoes
import identificacao_planta
import identificacao_visual
import chat_jarvis
import abrir_app_local


# 2. Registro dos pacotes — a única lista que precisa ser editada
#    quando um pacote novo for criado.
PACOTES_REGISTRADOS = [
    rede_jarvis,
    casa_inteligente,
    delegacao_ia,
    admin_terminal,
    configuracoes,
    identificacao_planta,
    identificacao_visual,
    chat_jarvis,
    abrir_app_local,
]


# 3. Ao montar a lista de tools do Gemini Live, depois das
#    FunctionDeclaration nativas do cliente:
function_declarations = list(function_declarations_nativas)

for pacote in PACOTES_REGISTRADOS:
    function_declarations.extend(
        pacote.obter_function_declarations()
    )

tools = [
    types.Tool(function_declarations=function_declarations)
]


# 4. No dispatch de tool_call (dentro do loop "for chamada in
#    tool_call.function_calls", antes do elif chain nativo):
resultado_pacote = None

for pacote in PACOTES_REGISTRADOS:
    resultado_pacote = await asyncio.to_thread(
        pacote.despachar,
        nome,      # chamada.name
        args,      # dict(chamada.args or {})
    )

    if resultado_pacote is not None:
        break

if resultado_pacote is not None:
    resultado = resultado_pacote

elif nome == "...":
    # tools nativas do cliente, inalteradas
    ...
```

## Wiring extra por pacote (além do contrato padrão)

Alguns pacotes precisam de um pouco mais do que as duas funções acima
— coisas específicas da sessão Gemini Live que não fazem sentido
generalizar no contrato (ex: o Jarvis "falar" algo por voz sem que o
usuário tenha pedido nada). Nesses casos, o pacote expõe funções
extras e o cliente precisa de um pequeno adaptador ("glue") — mas
mesmo assim, nenhuma lógica de negócio mora no cliente, só a ponte.

### `rede_jarvis`

Precisa de uma chamada de inicialização no `__init__` do worker (na
thread da GUI, antes de qualquer chamada de voz começar) e de dois
métodos de adaptação de sessão:

```python
# No __init__ do worker/cliente, uma vez (idempotente):
rede_jarvis.iniciar_rede_jarvis(
    callback_falar=self._falar_espontaneamente,
    callback_frame_remoto=self._receber_frame_remoto,
)


# Callback GENÉRICO (não é específico de rede_jarvis, apesar de ter
# nascido lá — ver seção admin_terminal abaixo para o segundo pacote
# que reaproveita o mesmo método): o Jarvis anuncia algo por voz
# espontaneamente (ex: um pedido de permissão remota chegando de
# outra máquina, ou o resultado de um comando administrativo
# confirmado fora da conversa).
def _falar_espontaneamente(self, texto):
    if not self.loop or not self.sessao:
        return

    asyncio.run_coroutine_threadsafe(
        self._enviar_anuncio_espontaneo(texto),
        self.loop,
    )


async def _enviar_anuncio_espontaneo(self, texto):
    await self.sessao.send_client_content(
        turns=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "[SISTEMA] Diga isso em voz alta agora, "
                            "com suas próprias palavras, de forma "
                            f"natural e breve: {texto}"
                        )
                    )
                ],
            )
        ],
        turn_complete=True,
    )


# Callback: um frame de visualização remota chegou e precisa ser
# injetado na sessão Live local (mesmo mecanismo da visualização
# contínua local, via send_realtime_input).
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
```

O código-fonte de referência (cópia funcionando, sempre atualizada)
está em `gemini/live_client_basic.py`, no `__init__` de
`GeminiLiveWorker` e nos métodos `_falar_espontaneamente`/
`_receber_frame_remoto`/`_enviar_anuncio_espontaneo`/
`_injetar_frame_remoto`.

### `casa_inteligente`

Sem wiring extra — só o contrato padrão
(`obter_function_declarations()`/`despachar()`). Não precisa de
callbacks de sessão, inicialização em background nem estado por
chamada de voz: cada ação é uma chamada de API HTTP pontual.

### `delegacao_ia`

Também sem wiring extra — mesmo caso do `casa_inteligente`: cada
delegação é uma chamada HTTP pontual e síncrona (com timeout curto e
fallback já resolvidos dentro do próprio pacote), sem callback de
sessão nem estado em background.

### `admin_terminal`

Precisa de uma chamada de inicialização no `__init__` do worker, reaproveitando o
**mesmo** `_falar_espontaneamente` já usado por `rede_jarvis` (não é um mecanismo
novo — os dois pacotes recebem uma referência ao mesmo método genérico do worker, sem
nenhuma dependência entre os pacotes em si):

```python
# No __init__ do worker/cliente, uma vez:
admin_terminal.iniciar_admin_terminal(
    callback_falar=self._falar_espontaneamente,
)
```

Esse callback só é usado quando um comando administrativo pendente de confirmação é
resolvido pela **notificação do Windows** (clique em "Permitir"/"Negar") ou pelo
**timeout** — casos em que a resposta chega numa thread de fundo, sem nenhuma
`tool_call` do Gemini esperando por ela, exatamente como o uso já existente em
`rede_jarvis`. Quando a confirmação vem por voz (`confirmar_comando_admin`), o
resultado é devolvido direto como resposta da própria tool — não passa por esse
callback. Ver `admin_terminal/confirmacao.py` para o porquê dessa distinção (nunca
foi enviado um novo `client_content` espontâneo enquanto uma `tool_call` de
`executar_comando_admin` ainda estivesse pendente de resposta — isso evitaria um
comportamento não testado da API Live).

`admin_terminal` não importa nada de `rede_jarvis` nem é acessível pelo canal remoto
de `rede_jarvis` (`TABELA_COMANDOS` de `rede_jarvis/comandos.py`) — são
funcionalidades deliberadamente desconectadas por enquanto (ver `CLAUDE.md`).

Além disso, `admin_terminal` depende de um passo de setup **manual**, fora do fluxo
normal do app: `python -m admin_terminal.setup` precisa ser rodado uma vez por
máquina (cria a Tarefa Agendada do Windows usada para elevação — ver
`admin_terminal/setup.py`). Isso não faz parte do wiring do cliente Gemini Live; é
uma etapa de infraestrutura da máquina, documentada no próprio pacote.

### `configuracoes`

Precisa de um sinalizador Qt genérico (`interfaces_extras/sinalizador.py`) e de UMA
linha de conexão numa thread principal — mas essa linha fica no arquivo de
**entrada** (`main_basic.py`), nunca em `ui/main_window_basic.py`, por decisão
explícita do projeto (a janela principal não deve saber nada sobre a tela de
configurações).

Motivo: `despachar("abrir_configuracoes", ...)` roda numa thread de fundo (como
qualquer `despachar()`, via `asyncio.to_thread`), mas uma janela Qt só pode ser
criada/mostrada na thread principal — então o pacote nunca cria a janela, só emite um
`Signal`:

```python
# interfaces_extras/sinalizador.py — QObject com o(s) Signal(s)
# usados por qualquer pacote que precise abrir uma janela extra.
# Instância única do processo, criada sob demanda (nunca no import
# do módulo — só na primeira chamada a obter_sinalizador(), depois
# que QApplication já existe).
class SinalizadorInterfacesExtras(QObject):
    solicitou_abrir_configuracoes = Signal()

_instancia = None

def obter_sinalizador():
    global _instancia
    if _instancia is None:
        _instancia = SinalizadorInterfacesExtras()
    return _instancia


# configuracoes/__init__.py — despachar() só emite:
def abrir_configuracoes():
    obter_sinalizador().solicitou_abrir_configuracoes.emit()
    return "Abrindo a tela de configurações."


# main_basic.py — a ÚNICA linha de conexão em thread principal,
# dentro de main(), depois de criar o QApplication:
obter_sinalizador().solicitou_abrir_configuracoes.connect(_abrir_configuracoes)

# E o slot (também em main_basic.py) que de fato cria a janela,
# guardando uma referência em variável de módulo pra não ser
# destruída pelo garbage collector assim que a função retornar:
_janela_configuracoes = None

def _abrir_configuracoes():
    global _janela_configuracoes
    from configuracoes.window import ConfiguracoesWindow
    _janela_configuracoes = ConfiguracoesWindow()
    _janela_configuracoes.show()
```

Um pacote futuro que precise abrir outra janela extra deve reaproveitar esse mesmo
`SinalizadorInterfacesExtras` (adicionando um `Signal` novo nele), em vez de criar um
mecanismo de threading próprio — e sua conexão também deve ficar em `main_basic.py`,
nunca em `ui/main_window_basic.py`.

#### O contrato extra deste pacote: `config_schema()`

`configuracoes/window.py` monta a tela lendo `config_schema()` do `config.py` de cada
pacote listado em `configuracoes/pacotes.py` (`PACOTES_COM_CONFIG` — uma lista
explícita separada de `PACOTES_REGISTRADOS`, porque nem todo pacote registrado no
cliente Gemini Live necessariamente expõe variáveis de `.env` configuráveis pela
tela). `config_schema()` retorna uma lista de dicts, um por variável:

```python
def config_schema():
    return [
        {
            "nome": "MQTT_HOST",           # nome exato da variável no .env
            "rotulo": "Host do broker MQTT",  # rótulo amigável exibido na tela
            "sensivel": False,              # True mascara o campo (API key/token/senha)
            "obrigatoria": True,            # True adiciona um "*" ao rótulo
        },
        ...
    ]
```

**Ao criar um pacote novo com variáveis de `.env`**: além dos passos já descritos
acima (import + `PACOTES_REGISTRADOS`), adicione `config_schema()` ao `config.py` do
pacote cobrindo as variáveis reais que ele lê (nunca invente nomes), e registre o
pacote em `configuracoes/pacotes.py` (`PACOTES_COM_CONFIG`) — só assim ele aparece
como uma seção na tela de configurações. Nenhuma outra linha de `configuracoes/`
muda.

### `identificacao_planta` e `identificacao_visual`

Essas duas tools (`identificar_planta` e `consultar_segunda_opiniao_visual`) são a
única exceção ao loop de despacho genérico até agora, e compartilham o mesmo wiring
extra em dois pontos: **antes** e **depois** do loop `for pacote in
PACOTES_REGISTRADOS`.

**Antes do loop** — nenhuma das duas tem uma imagem como parâmetro que o Gemini
preenche; a captura precisa vir do cliente (reaproveitando
`vision/camera_capture.py`, a mesma função já usada por `analisar_camera`), injetada
em `args` antes de despachar:

```python
# Dentro de processar_chamada_de_funcao, ANTES do loop "for pacote
# in PACOTES_REGISTRADOS":
if nome in ("identificar_planta", "consultar_segunda_opiniao_visual"):
    self.status_recebido.emit("Capturando imagem da câmera...")
    args["imagem_bytes"] = capturar_camera_bytes()

# O loop genérico de despacho continua exatamente igual depois disso
# — cada pacote recebe args já com a imagem dentro, como qualquer
# outro pacote receberia argumentos vindos do Gemini.
# identificacao_visual também recebe um parâmetro REAL vindo do
# Gemini (args["pergunta"]) — a pergunta exata que o usuário fez,
# preenchida pelo modelo a partir da conversa, igual qualquer outro
# parâmetro de qualquer outra tool.
```

**Depois do loop** — as duas tools consultam uma fonte externa (Pl@ntNet ou Mistral)
que só vê a imagem uma vez, sem "memória" da conversa. Pra o Gemini não apenas
repetir esse resultado externo sem checagem, a MESMA imagem é reenviada a ele (via
`send_client_content`, com uma instrução de comparar com a própria leitura visual)
antes do `tool_response` da chamada original ser enviado — mesma ordem já usada por
`analisar_tela`/`analisar_camera` via `processar_funcao_visual` (a imagem chega
primeiro por `send_client_content`, o `tool_response` só fecha a chamada depois):

```python
if resultado_pacote is not None:
    resultado = resultado_pacote

    if nome in (
        "identificar_planta", "consultar_segunda_opiniao_visual"
    ) and args.get("imagem_bytes"):
        await self.enviar_imagem_para_cruzamento(
            args["imagem_bytes"],
            resultado,
            contexto="identificação de planta (Pl@ntNet)",  # ou "segunda opinião visual (Mistral)"
        )
```

`enviar_imagem_para_cruzamento(self, imagem_bytes, resultado_externo, contexto)` é um
método novo e genérico do worker (ao lado de `_enviar_anuncio_espontaneo`) — reenvia a
imagem com `inline_data` + um texto `[SISTEMA]` explicando de qual fonte veio o
resultado e pedindo pro Gemini dizer explicitamente se concorda ou diverge, nunca
repassar o resultado externo como se fosse a única opinião.

Se um pacote futuro precisar de outro dado que só o cliente pode produzir (outro tipo
de captura, outro estado da sessão) — ou precisar do mesmo "reenviar a imagem pra
conferência" — o mesmo padrão se aplica: um pequeno bloco `if nome == "..."` antes
e/ou depois do loop genérico, nunca lógica de negócio dentro do próprio pacote (que
não tem acesso a `vision/`, `self.sessao`, etc.).

Fora isso, nenhum dos dois pacotes precisa de mais wiring — cada consulta é uma
chamada HTTP pontual e síncrona (Pl@ntNet ou Mistral), sem callback de sessão nem
estado em background, mesmo caso de `casa_inteligente`/`delegacao_ia`.

### `explorador_windows`

Caso diferente de todos os anteriores: este pacote **não tem nenhuma tool de voz
própria** — `obter_function_declarations()` retorna `[]` e `despachar()` nunca
reconhece nada. Ele segue o contrato padrão (`obter_function_declarations()`/
`despachar()`) só por consistência estrutural com o resto do projeto, mas por não
expor nada, **não entra em `PACOTES_REGISTRADOS`** — registrá-lo ali só adicionaria
uma chamada de `despachar()` sempre-`None` a cada tool_call de qualquer pacote, sem
nenhum benefício.

`obter_arquivo_selecionado()` é chamado **diretamente** por quem precisar dele —
igual `capturar_camera_bytes()`/`capturar_tela_bytes()` já são — não pelo mecanismo
de tools. Hoje o único consumidor é a tool **nativa** `enviar_email` (não um pacote),
dentro do `elif nome == "enviar_email":` em `processar_chamada_de_funcao`:

```python
import explorador_windows  # topo do arquivo, junto dos outros imports

# ...

elif nome == "enviar_email":
    usar_arquivo_selecionado = bool(args.get("usar_arquivo_selecionado", False))
    caminho_anexo = None
    falha_anexo = None

    if usar_arquivo_selecionado:
        sucesso_arquivo, resultado_arquivo = await asyncio.to_thread(
            explorador_windows.obter_arquivo_selecionado
        )

        if not sucesso_arquivo:
            falha_anexo = "..."  # nenhum arquivo encontrado — não envia
        elif len(resultado_arquivo) > 1:
            falha_anexo = "..."  # ambíguo — não envia, pede pra escolher
        else:
            caminho_anexo = resultado_arquivo[0]

    if falha_anexo:
        resultado = falha_anexo
    else:
        resultado = await asyncio.to_thread(
            enviar_email, destinatario, assunto, corpo, caminho_anexo
        )
```

Se um dia `enviar_email` for migrado pra dentro de um pacote isolado (`mailer/` não
é um pacote de tools hoje, é um módulo puro reaproveitado pela tool nativa), esse
mesmo trecho — captura de um dado só o cliente sabe produzir, ANTES de decidir o que
despachar — se aplicaria da mesma forma dentro do `despachar()` desse pacote,
seguindo o mesmo princípio.

### `chat_jarvis`

Segue o contrato padrão pras duas tools (`abrir_chat`/`abrir_envio_arquivo` — mesmo
padrão de `configuracoes`, `despachar()` só emite um sinal), **mais uma exceção
real**: as duas janelas (`ui/chat_window.py`, `ui/envio_arquivo_window.py`) precisam
mandar dado NOVO pra dentro da sessão Live já em andamento — texto digitado, imagem
ou texto de arquivo — não só disparar um sinal de abrir janela. Isso não cabe dentro
do pacote (que não tem acesso a `self.sessao`/`self.loop`), então o worker
(`GeminiLiveWorker`, em `gemini/live_client_basic.py`) expõe dois métodos públicos
pra essa ponte:

```python
# Chamado pela janela de chat/envio de arquivo (thread principal),
# depois de obter a instância ATUAL do worker via um getter (nunca
# uma referência fixa — ver "Como as janelas acham o worker certo"
# abaixo). Faz asyncio.run_coroutine_threadsafe no loop do worker —
# mesma técnica de _falar_espontaneamente, só que na direção
# contrária (de fora pra dentro, não de dentro pra fora).
worker.enviar_texto_da_ui(texto)                                    # -> bool
worker.enviar_imagem_da_ui(imagem_bytes, mime_type, texto_contexto) # -> bool
```

Os dois retornam `False` sem lançar exceção se não houver sessão ativa (`self.loop`/
`self.sessao` ainda `None`, ou a chamada já terminou) — quem chama decide o que
mostrar ao usuário nesse caso (ver `ui/chat_window.py`/`ui/envio_arquivo_window.py`).

**Por que `send_realtime_input`, não `send_client_content`**: as demais features de
imagem deste projeto (`enviar_camera_para_gemini`, `_enviar_anuncio_espontaneo`,
`enviar_imagem_para_cruzamento`) usam `send_client_content` com sucesso comprovado —
mas a documentação oficial do modelo configurado (`gemini-3.1-flash-live-preview`,
`core/config.py`) diz que `send_client_content` só é garantido pra semear o histórico
inicial da sessão, não pra atualizações durante a conversa (*"to send text updates
during the conversation, use `send_realtime_input` instead"*). Como este é código
novo, usa o mecanismo oficialmente correto (`send_realtime_input(text=...)` pra
texto, `send_realtime_input(video=...)` pra imagem — mesmo campo já usado por
`_injetar_frame_remoto`) em vez de replicar um padrão que funciona na prática mas
está fora do contrato documentado. Os usos existentes de `send_client_content` **não
foram alterados** por essa descoberta — decisão consciente do usuário, registrada
aqui e em `CLAUDE.md`, não um ajuste feito por conta própria.

**Como as janelas acham o worker certo**: `GeminiLiveWorker` é recriado a cada
chamada de voz (`self.live_worker = None` entre chamadas — ver
`ui/main_window_basic.py`), então as janelas nunca guardam uma referência fixa.
`main_basic.py` define um getter (`_obter_worker_ativo()`) que lê
`window.live_worker` de novo a cada chamada, e passa esse getter (não um objeto) pra
`ChatWindow`/`EnvioArquivoWindow` no momento de criá-las — assim a janela continua
funcionando mesmo que a chamada termine e outra comece enquanto ela está aberta.
`window` (a `MainWindow` criada em `main()`) é guardada numa variável de módulo só
pra isso; `live_worker` já era um atributo público de `MainWindow`, então isso não
exigiu nenhuma edição em `ui/main_window_basic.py`.

**A direção contrária (resposta do Gemini → janela de chat)** usa o sinalizador
compartilhado, não um Signal do worker — ver `resposta_texto_recebida` em
`interfaces_extras/sinalizador.py` e o comentário lá explicando por quê (mesma razão:
o worker muda de instância a cada chamada, e reconectar um Signal a cada troca seria
mais frágil que emitir sempre pro mesmo objeto persistente). `GeminiLiveWorker`
precisou de `output_audio_transcription=types.AudioTranscriptionConfig()` a mais no
`LiveConnectConfig` pra essa transcrição existir — confirmado no SDK instalado antes
de usar (`resposta.server_content.output_transcription.text`/`.finished`), não
assumido.

### `abrir_app_local`

Sem wiring extra — só o contrato padrão (`obter_function_declarations()`/
`despachar()`), mesmo caso de `casa_inteligente`/`delegacao_ia`. Nenhum callback de
sessão, inicialização em background ou estado por chamada de voz: busca (via
subprocess pro PowerShell) e abertura de app são ambas pontuais e síncronas.

## Checklist para religar tudo em um cliente novo

1. Copie o trecho da seção "Trecho pronto para copiar" (imports,
   `PACOTES_REGISTRADOS`, extensão de `tools`, loop de despacho).
2. Para cada pacote listado na seção "Wiring extra por pacote" acima,
   copie também o wiring específico dele.
3. Rode o app e confirme que `PACOTES_REGISTRADOS` aparece com todos
   os pacotes esperados e que uma tool de cada pacote funciona por
   voz.
