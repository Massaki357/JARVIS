# Integração dos pacotes de tools com o cliente Gemini Live

Este arquivo é a fonte da verdade de como religar os pacotes isolados
(`jarvis/pacotes/rede_jarvis/`, `jarvis/pacotes/casa_inteligente/`, `jarvis/pacotes/delegacao_ia/`, `jarvis/pacotes/admin_terminal/`,
`jarvis/pacotes/configuracoes/`, `jarvis/pacotes/identificacao_planta/`, `jarvis/pacotes/identificacao_visual/`,
`jarvis/pacotes/explorador_windows/`, `jarvis/pacotes/chat_jarvis/`, `jarvis/pacotes/abrir_app_local/`, `jarvis/pacotes/discord_jarvis/`, e
outros que vierem depois) a QUALQUER arquivo cliente Gemini Live — seja o
`jarvis/gemini/cliente_live.py` atual (temporário, será substituído quando a versão
completa do curso chegar) ou o arquivo cliente da versão final.

**Atualize este arquivo toda vez que um pacote novo for criado, ou que
a forma de religar um pacote existente mudar.**

## Por que esse padrão existe

Três arquivos vieram do projeto do curso e são temporários: `main.py`,
`jarvis/gemini/cliente_live.py` e `jarvis/ui/janela_principal.py` (antes
`main_basic.py`, `gemini/live_client_basic.py` e
`ui/main_window_basic.py` — o sufixo `_basic` sumiu na reorganização de
pastas, mas o status deles é exatamente o mesmo). Nenhuma lógica
importante pode depender de edições feitas diretamente neles — a
integração precisa ser fácil de "religar" em outro arquivo cliente no
futuro, sem precisar reimplementar nada.

## Onde cada coisa mora

```
main.py                     ponto de entrada (python main.py)
config.json                 preferências locais desta máquina
dados/                      estado gerado pelo app (memória, caches, logs)
docs/INTEGRATION.md         este arquivo
jarvis/
  caminhos.py               RAIZ_PROJETO, PASTA_DADOS, PASTA_LOGS
  nucleo/                   config.py, preferencias.py, sinalizador.py, prompts/
  gemini/cliente_live.py    o worker da sessão Live
  ui/                       janela_principal, janela_chat,
                            janela_envio_arquivo, janela_camera
  servicos/                 visao/, email/, memoria/ (infra compartilhada)
  pacotes/                  um subpacote por integração/ferramenta
```

Nenhum arquivo do projeto calcula sozinho onde fica a raiz contando
`.parent` — quem precisa de um caminho fora do próprio código importa de
`jarvis/caminhos.py`. A única exceção é
`jarvis/pacotes/admin_terminal/runner_elevado.py`, que a Tarefa Agendada
executa como script solto (a raiz não está no `sys.path`, então ele não
consegue importar `jarvis`); o próprio arquivo explica isso num
comentário.

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
from jarvis.pacotes import rede_jarvis
from jarvis.pacotes import casa_inteligente
from jarvis.pacotes import delegacao_ia
from jarvis.pacotes import admin_terminal
from jarvis.pacotes import configuracoes
from jarvis.pacotes import identificacao_planta
from jarvis.pacotes import identificacao_visual
from jarvis.pacotes import chat_jarvis
from jarvis.pacotes import abrir_app_local
from jarvis.pacotes import discord_jarvis


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
    discord_jarvis,
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
está em `jarvis/gemini/cliente_live.py`, no `__init__` de
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
callback. Ver `jarvis/pacotes/admin_terminal/confirmacao.py` para o porquê dessa distinção (nunca
foi enviado um novo `client_content` espontâneo enquanto uma `tool_call` de
`executar_comando_admin` ainda estivesse pendente de resposta — isso evitaria um
comportamento não testado da API Live).

`admin_terminal` não importa nada de `rede_jarvis` nem é acessível pelo canal remoto
de `rede_jarvis` (`TABELA_COMANDOS` de `jarvis/pacotes/rede_jarvis/comandos.py`) — são
funcionalidades deliberadamente desconectadas por enquanto (ver `CLAUDE.md`).

Além disso, `admin_terminal` depende de um passo de setup **manual**, fora do fluxo
normal do app: `python -m jarvis.pacotes.admin_terminal.setup` precisa ser rodado uma vez por
máquina (cria a Tarefa Agendada do Windows usada para elevação — ver
`jarvis/pacotes/admin_terminal/setup.py`). Isso não faz parte do wiring do cliente Gemini Live; é
uma etapa de infraestrutura da máquina, documentada no próprio pacote.

### `configuracoes`

Precisa de um sinalizador Qt genérico (`jarvis/nucleo/sinalizador.py`) e de UMA
linha de conexão numa thread principal — mas essa linha fica no arquivo de
**entrada** (`main.py`), nunca em `jarvis/ui/janela_principal.py`, por decisão
explícita do projeto (a janela principal não deve saber nada sobre a tela de
configurações).

Motivo: `despachar("abrir_configuracoes", ...)` roda numa thread de fundo (como
qualquer `despachar()`, via `asyncio.to_thread`), mas uma janela Qt só pode ser
criada/mostrada na thread principal — então o pacote nunca cria a janela, só emite um
`Signal`:

```python
# jarvis/nucleo/sinalizador.py — QObject com o(s) Signal(s)
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


# jarvis/pacotes/configuracoes/__init__.py — despachar() só emite:
def abrir_configuracoes():
    obter_sinalizador().solicitou_abrir_configuracoes.emit()
    return "Abrindo a tela de configurações."


# main.py — a ÚNICA linha de conexão em thread principal,
# dentro de main(), depois de criar o QApplication:
obter_sinalizador().solicitou_abrir_configuracoes.connect(_abrir_configuracoes)

# E o slot (também em main.py) que de fato cria a janela,
# guardando uma referência em variável de módulo pra não ser
# destruída pelo garbage collector assim que a função retornar:
_janela_configuracoes = None

def _abrir_configuracoes():
    global _janela_configuracoes
    from jarvis.pacotes.configuracoes.window import ConfiguracoesWindow
    _janela_configuracoes = ConfiguracoesWindow()
    _janela_configuracoes.show()
```

Um pacote futuro que precise abrir outra janela extra deve reaproveitar esse mesmo
`SinalizadorInterfacesExtras` (adicionando um `Signal` novo nele), em vez de criar um
mecanismo de threading próprio — e sua conexão também deve ficar em `main.py`,
nunca em `jarvis/ui/janela_principal.py`.

#### O contrato extra deste pacote: `config_schema()`

`jarvis/pacotes/configuracoes/window.py` monta a tela lendo `config_schema()` do `config.py` de cada
pacote listado em `jarvis/pacotes/configuracoes/pacotes.py` (`PACOTES_COM_CONFIG` — uma lista
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
pacote em `jarvis/pacotes/configuracoes/pacotes.py` (`PACOTES_COM_CONFIG`) — só assim ele aparece
como uma seção na tela de configurações. Nenhuma outra linha de `jarvis/pacotes/configuracoes/`
muda.

### `identificacao_planta` e `identificacao_visual`

Essas duas tools (`identificar_planta` e `consultar_segunda_opiniao_visual`) são a
única exceção ao loop de despacho genérico até agora, e compartilham o mesmo wiring
extra em dois pontos: **antes** e **depois** do loop `for pacote in
PACOTES_REGISTRADOS`.

**Antes do loop** — nenhuma das duas tem uma imagem como parâmetro que o Gemini
preenche; a captura precisa vir do cliente (reaproveitando
`jarvis/servicos/visao/captura_camera.py`, a mesma função já usada por `analisar_camera`), injetada
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
não tem acesso a `jarvis/servicos/visao/`, `self.sessao`, etc.).

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
from jarvis.pacotes import explorador_windows  # topo do arquivo, junto dos outros imports

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

Se um dia `enviar_email` for migrado pra dentro de um pacote isolado (`jarvis/servicos/email/` não
é um pacote de tools hoje, é um módulo puro reaproveitado pela tool nativa), esse
mesmo trecho — captura de um dado só o cliente sabe produzir, ANTES de decidir o que
despachar — se aplicaria da mesma forma dentro do `despachar()` desse pacote,
seguindo o mesmo princípio.

### `chat_jarvis`

Segue o contrato padrão pras duas tools (`abrir_chat`/`abrir_envio_arquivo` — mesmo
padrão de `configuracoes`, `despachar()` só emite um sinal), **mais uma exceção
real**: as duas janelas (`jarvis/ui/janela_chat.py`, `jarvis/ui/janela_envio_arquivo.py`) precisam
mandar dado NOVO pra dentro da sessão Live já em andamento — texto digitado, imagem
ou texto de arquivo — não só disparar um sinal de abrir janela. Isso não cabe dentro
do pacote (que não tem acesso a `self.sessao`/`self.loop`), então o worker
(`GeminiLiveWorker`, em `jarvis/gemini/cliente_live.py`) expõe dois métodos públicos
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
mostrar ao usuário nesse caso (ver `jarvis/ui/janela_chat.py`/`jarvis/ui/janela_envio_arquivo.py`).

**Por que `send_realtime_input`, não `send_client_content`**: as demais features de
imagem deste projeto (`enviar_camera_para_gemini`, `_enviar_anuncio_espontaneo`,
`enviar_imagem_para_cruzamento`) usam `send_client_content` com sucesso comprovado —
mas a documentação oficial do modelo configurado (`gemini-3.1-flash-live-preview`,
`jarvis/nucleo/config.py`) diz que `send_client_content` só é garantido pra semear o histórico
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
`jarvis/ui/janela_principal.py`), então as janelas nunca guardam uma referência fixa.
`main.py` define um getter (`_obter_worker_ativo()`) que lê
`window.live_worker` de novo a cada chamada, e passa esse getter (não um objeto) pra
`ChatWindow`/`EnvioArquivoWindow` no momento de criá-las — assim a janela continua
funcionando mesmo que a chamada termine e outra comece enquanto ela está aberta.
`window` (a `MainWindow` criada em `main()`) é guardada numa variável de módulo só
pra isso; `live_worker` já era um atributo público de `MainWindow`, então isso não
exigiu nenhuma edição em `jarvis/ui/janela_principal.py`.

**A direção contrária (resposta do Gemini → janela de chat)** usa o sinalizador
compartilhado, não um Signal do worker — ver `resposta_texto_recebida` em
`jarvis/nucleo/sinalizador.py` e o comentário lá explicando por quê (mesma razão:
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

### `discord_jarvis`

Precisa de uma chamada de inicialização no `__init__` do worker — mesmo padrão de
`rede_jarvis.iniciar_rede_jarvis`/`admin_terminal.iniciar_admin_terminal`:

```python
# No __init__ do worker/cliente, uma vez (idempotente):
discord_jarvis.iniciar_discord_jarvis()
```

Diferente de `rede_jarvis` (que usa paho-mqtt, síncrono e thread-safe por natureza),
`discord_jarvis` usa `discord.py`, que exige um loop `asyncio` próprio vivo o tempo
todo. `iniciar_discord_jarvis()` sobe uma thread de fundo dedicada com seu próprio
loop (`jarvis/pacotes/discord_jarvis/cliente.py`), rodando `cliente.start(token)` até a conexão
cair — mesmo padrão de loop de fundo dedicado já usado em
`jarvis/pacotes/rede_jarvis/visualizacao_remota.py`. Chamadas síncronas vindas de `despachar()`
(que já roda em thread separada via `asyncio.to_thread`) usam
`asyncio.run_coroutine_threadsafe(corrotina, loop_do_bot).result(timeout=...)` pra
entrar nesse loop e esperar o resultado — a mesma técnica de
`visualizacao_remota.py`, não um mecanismo novo.

**Setup fora do código, obrigatório antes de funcionar**: além de `DISCORD_BOT_TOKEN`
no `.env`, o bot precisa ter **"Server Members Intent"** e **"Message Content
Intent"** ativadas em Privileged Gateway Intents no Developer Portal
(discord.com/developers/applications) — confirmado ao vivo: sem isso, a conexão
falha explicitamente (`discord.errors.PrivilegedIntentsRequired`), não falha
silenciosamente. O bot também precisa estar convidado num servidor onde as pessoas
que vão receber DM estejam — `buscar_membro`/`buscar_canal` só enxergam servidores
em comum com o bot.

### `camera_preview`

Mesmo padrão de `configuracoes` (sinalizador genérico, `despachar()` só emite —
ver a seção `configuracoes` acima pro trecho completo do mecanismo), com duas
tools em vez de uma (`abrir_camera`/`fechar_camera`) e uma diferença: a janela
(`jarvis/ui/janela_camera.py`, `JanelaCamera`) precisa ser **focada em vez de duplicada**
se já estiver aberta, e **avisar `main.py` quando fecha** (pelo X ou por
`fechar_camera`), pra que uma abertura seguinte crie uma janela nova em vez de
achar que a antiga ainda existe — mesmo padrão de `ao_fechar` já usado por
`ChatWindow`/`EnvioArquivoWindow` (ver seção `chat_jarvis` acima):

```python
# jarvis/nucleo/sinalizador.py — dois Signals novos, mesma classe:
solicitou_abrir_camera = Signal()
solicitou_fechar_camera = Signal()

# main.py:
_janela_camera = None

def _abrir_camera():
    global _janela_camera
    if _janela_camera is not None:
        _janela_camera.raise_()
        _janela_camera.activateWindow()
        return
    from jarvis.ui.janela_camera import JanelaCamera
    _janela_camera = JanelaCamera(ao_fechar=_ao_fechar_camera)
    _janela_camera.show()

def _fechar_camera():
    if _janela_camera is not None:
        _janela_camera.close()

def _ao_fechar_camera():
    global _janela_camera
    _janela_camera = None

obter_sinalizador().solicitou_abrir_camera.connect(_abrir_camera)
obter_sinalizador().solicitou_fechar_camera.connect(_fechar_camera)
```

**Risco de concorrência no dispositivo — confirmado ao vivo antes de implementar,
não assumido**: a maioria das webcams (testado aqui via backend MSMF do OpenCV, o
padrão no Windows) não erra ao abrir um segundo `cv2.VideoCapture(0)` enquanto um
primeiro já está aberto, mas o segundo handle interfere na leitura do primeiro
enquanto ambos coexistem — um teste real mostrou o handle já aberto perdendo
100% dos frames durante toda a janela em que um segundo handle ficava aberto,
voltando ao normal assim que o segundo era liberado. Por isso `JanelaCamera` e
`vision.camera_capture.capturar_camera_bytes()` (usada por `analisar_camera`,
`tirar_foto_camera`, `identificar_planta`, `consultar_segunda_opiniao_visual`)
**compartilham o MESMO handle** em vez de abrir um cada:

```python
# jarvis/servicos/visao/captura_camera.py — API do handle compartilhado:
abrir_camera_compartilhada()        # -> bool; idempotente; só chamada por JanelaCamera
fechar_camera_compartilhada()       # só chamada por JanelaCamera, no closeEvent
camera_compartilhada_esta_aberta()  # -> bool
ler_frame_camera_compartilhada()    # -> (bool, frame_bgr | None); sob lock
```

`JanelaCamera` é a DONA do ciclo de vida do handle compartilhado (abre no
`__init__`, fecha no `closeEvent`) — ela é quem chama
`abrir_camera_compartilhada()`/`fechar_camera_compartilhada()`.
`capturar_camera_bytes()` nunca abre nem fecha o handle compartilhado, só lê
dele quando `camera_compartilhada_esta_aberta()` é `True`; quando é `False`
(preview fechado, caso normal), seu comportamento original — abrir seu próprio
`cv2.VideoCapture(0)`, aquecer, ler, liberar — continua idêntico e inalterado.
Um `threading.Lock` protege as leituras/aberturas/fechamentos contra o QTimer do
preview (thread principal) e uma captura pontual (thread do worker Gemini)
colidindo.

Um pacote futuro que também precise manter um recurso de hardware aberto
continuamente (não só uma janela) deveria seguir esse mesmo formato — dono único
do ciclo de vida do recurso, ponto de leitura compartilhado sob lock, e o
consumidor pontual (`capturar_camera_bytes`) só lê se já estiver aberto, nunca
abre por conta própria.

### `ativacao_voz`

**Não é um pacote de tools** (mesmo caso de `explorador_windows`) —
`obter_function_declarations()` retorna `[]` e `despachar()` sempre retorna `None`,
só por consistência de forma com o resto do projeto; não entra em
`PACOTES_REGISTRADOS`. O motivo: não faz sentido uma tool "ative a ativação por voz"
chamável DENTRO de uma sessão Gemini já em andamento — o próprio propósito deste
pacote é decidir quando uma sessão COMEÇA, então ele é usado de duas formas
completamente fora do fluxo normal de `despachar()`:

1. **`main.py` chama `ativacao_voz.iniciar(callback_ativacao=...)` uma única
   vez**, dentro de `main()`, depois que a janela principal (`window`) já existe —
   o callback roda numa thread de fundo PRÓPRIA do detector (nunca a thread da GUI),
   então só faz uma coisa thread-safe dentro dele: emitir
   `solicitou_iniciar_chamada_por_voz` (novo Signal em
   `jarvis/nucleo/sinalizador.py`, mesmo sinalizador genérico usado por
   `configuracoes`/`camera_preview`). O slot conectado a esse Signal
   (`_iniciar_chamada_por_voz`, em `main.py`) roda na thread principal e chama
   `window.alternar_chamada()` — o MESMO método que o clique do botão já chama,
   reaproveitado, não duplicado.

2. **`GeminiLiveWorker` (`jarvis/gemini/cliente_live.py`) chama
   `ativacao_voz.pausar()`/`ativacao_voz.retomar()` diretamente**, ao redor do
   próprio ciclo de vida de `executar()` — `pausar()` como a primeira linha de
   `executar()` (antes até de conectar no Gemini), `retomar()` logo depois de
   `self.sessao = None` no final. Isso não é uma exceção nova ao padrão — é o mesmo
   tipo de chamada direta (fora de `despachar()`) que
   `rede_jarvis.iniciar_rede_jarvis()`/`admin_terminal.iniciar_admin_terminal()` já
   fazem a partir de `__init__`, só que aqui em dois pontos do ciclo de vida em vez
   de um.

```python
# jarvis/pacotes/ativacao_voz/detector.py — API pública, chamada direta (nunca via despachar()):
iniciar(callback_ativacao)  # -> bool; chamado uma vez, em main.py
pausar()                    # chamado por GeminiLiveWorker, início de executar()
retomar()                   # chamado por GeminiLiveWorker, fim de executar()
esta_ativo()                # -> bool
```

**Risco de concorrência no dispositivo — mesmo cuidado já confirmado ao vivo pra
`camera_preview` (ver seção acima), aplicado aqui ao microfone**: o detector de
ativação por voz e `GeminiLiveWorker.enviar_microfone()` nunca podem ter o
microfone aberto ao mesmo tempo. `pausar()` é síncrona e bloqueia (`thread.join()`)
até o stream do detector estar de fato fechado antes de retornar — por isso é
chamada como a primeiríssima coisa em `executar()`, garantindo que o microfone já
esteja livre antes de `enviar_microfone` tentar abri-lo.

**Vosk, não Picovoice Porcupine — pivô deliberado no meio da tarefa, não o design
original.** A primeira versão usava Porcupine (motor de wake-word dedicado),
confirmado ao vivo que ainda exige uma AccessKey gratuita da Picovoice
(`console.picovoice.ai`, cadastro manual). O usuário então pediu explicitamente uma
alternativa sem conta nenhuma ("só com python mesmo, reconhecendo o que foi falado
e comparando com o nome") — o detector inteiro foi reescrito em cima do pacote
`vosk` (reconhecimento de voz genérico, offline, sem chave/conta nenhuma):
`Model(lang="pt")` baixa sozinho (confirmado ao vivo: ~31MB) um modelo pequeno em
português de `alphacephei.com` na primeira vez que roda, e guarda em cache local
(`~/AppData/Local/vosk` no Windows) depois disso — nenhum cadastro em lugar nenhum
do fluxo. Trade-off avisado explicitamente ao usuário: reconhecimento de voz
genérico é menos preciso pra detectar UMA palavra específica do que um motor de
wake-word dedicado seria — falsos negativos (principalmente com a palavra colada
sem pausa em outras) são mais prováveis do que seriam com Porcupine.

**Carregamento do modelo acontece DENTRO da própria thread de detecção
(`_loop_deteccao`), nunca em `iniciar()`/`_abrir()`** — de propósito, pra
`main.py.main()` nunca travar a inicialização do app esperando um possível
download demorado na primeira vez. `_modelo` (o `vosk.Model` carregado, pesado) é
um singleton em nível de módulo, carregado uma vez e reaproveitado em todo ciclo de
`pausar()`/`retomar()` — só o `KaldiRecognizer` (leve) e o stream do `sounddevice`
são recriados a cada ciclo. `pausar()` usa um timeout generoso (30s) no
`thread.join()` especificamente pra cobrir o caso raro de uma chamada manual
começar enquanto o download do modelo (só na primeiríssima vez) ainda está
rodando; em qualquer execução seguinte (modelo já em cache), isso resolve quase
instantaneamente (confirmado ao vivo, ~0,1s).

**Detecção**: `reconhecedor.AcceptWaveform()`/`PartialResult()`/`Result()` devolvem
strings JSON (confirmado ao vivo contra o código-fonte real do `vosk-api`, não só a
doc em prosa) — o texto de `PartialResult()` (campo `"partial"`) é checado a cada
bloco (não só o `Result()` finalizado, campo `"text"`), pra latência menor, já que
o Vosk só finaliza um trecho numa pausa. A comparação (`_contem_palavra_ativacao`)
normaliza acento/caixa (mesma técnica `_normalizar` já copiada de forma
independente em `abrir_app_local`/`discord_jarvis`), tenta a frase inteira como
substring contígua primeiro e, se a ativação tiver mais de uma palavra e isso não
bater, exige que TODAS as palavras-alvo apareçam em algum lugar do texto (não
necessariamente adjacentes, via `_palavra_esta_presente`, que por sua vez cai pra
`difflib.get_close_matches`, mesmo corte 0.72 já usado em outros pacotes) — cobre
frases naturais como "iniciar A chamada" (artigo no meio), que não bateriam como
substring exato de "iniciar chamada".

**"jarvis" era o padrão original e é definitivamente impossível de reconhecer —
bug real encontrado ao vivo durante teste, não questão de ajuste fino.** O modelo
"small" em português do Vosk tem vocabulário FECHADO (um grafo de decodificação
fixo, `HCLr.fst`/`Gr.fst`) — uma palavra ausente dele nunca é reconhecida, não
importa quão claramente seja dita. Confirmado de duas formas:
`Model.vosk_model_find_word("jarvis")` retorna "não encontrado", e até o modo de
gramática restrita do Vosk (`KaldiRecognizer(model, rate, grammar_json)`, pensado
exatamente pra esse tipo de correspondência com vocabulário pequeno e fixo) loga
`Ignoring word missing in vocabulary: 'jarvis'` e descarta a palavra silenciosamente
da gramática. Um teste real com microfone confirmou o sintoma exato: o modelo ficava
substituindo por palavras não relacionadas que ESTAVAM no vocabulário ("games",
"jogos", "adicione") em vez de chegar perto de "jarvis" em algum momento. O padrão
foi trocado pra **`"iniciar chamada"`** — as duas palavras confirmadas no
vocabulário antes de virar o padrão (ver `jarvis/pacotes/ativacao_voz/config.py`). Qualquer
palavra/frase de ativação nova (padrão do projeto ou escolha do usuário) precisa
ser conferida contra o vocabulário real do modelo da mesma forma — nunca assumir
que "parece uma palavra normal" é suficiente.

**sounddevice, não `pvrecorder`/PyAudio**: reaproveitado via leitura BLOQUEANTE
(`stream.read(TAMANHO_BLOCO_VOSK)`, confirmada com um teste real antes de
implementar), em vez do modo com callback já usado por `enviar_microfone`, já que o
detector roda numa thread própria simples, sem precisar interoperar com nenhum loop
`asyncio`.

**Encerramento por inatividade** (`TIMEOUT_INATIVIDADE_SEGUNDOS`, `jarvis/nucleo/config.py`)
é uma feature separada, sem relação de código com o detector de ativação além de
terem sido pedidas juntas — vive inteiramente em `jarvis/gemini/cliente_live.py`:
`GeminiLiveWorker.verificar_inatividade()` roda como mais uma das tarefas
concorrentes de `executar()` (junto de `enviar_microfone`/`receber_audio`/
`reproduzir_audio`), checando periodicamente `self.timestamp_ultima_atividade`
(atualizado só quando `resposta.data` chega ou um `tool_call` é processado — nunca
por áudio bruto do microfone). Ao expirar, reaproveita
`_enviar_anuncio_espontaneo()` (mesmo mecanismo de fala espontânea de
`rede_jarvis`/`admin_terminal`) pra avisar por voz, e depois reaproveita
`encerrar_apos_resposta()` (a mesma tarefa que a tool `encerrar_chamada` já
agenda) pra encerrar — nenhum caminho de encerramento paralelo foi criado.

## Interrupção de fala (config.json)

Diferente de tudo mais neste documento, isto **não é uma tool isolável** — é uma
mudança no próprio núcleo do loop de áudio (`enviar_microfone`/`receber_audio` do
cliente). Não segue o contrato `obter_function_declarations()`/`despachar()`. Esta
seção existe pra reimplementar o CONCEITO manualmente num cliente novo (a estrutura
do loop pode ser bem diferente lá) — leia sozinha, sem depender do resto do
documento.

### O que essa feature faz

Por padrão, o cliente ignora o microfone inteiro enquanto o jarvis está falando
(`self.alfred_falando == True`) — evita que ele escute a própria voz (eco). Isso
significa que o usuário nunca consegue interromper uma resposta falando por cima;
precisa esperar o jarvis terminar. `config.json` liga um modo opcional onde isso
deixa de valer: o microfone continua sendo capturado e enviado mesmo com o jarvis
falando, e o cliente reage quando o servidor avisa que a fala foi interrompida.

### Formato do config.json (raiz do projeto)

```json
{
  "config": [
    { "interrupcao": false }
  ]
}
```

- `interrupcao: false`, arquivo ausente, campo ausente, ou JSON inválido → todos
  caem no mesmo padrão: `False` (comportamento de sempre, sem interrupção).
- `interrupcao: true` → habilita o modo de interrupção.
- O valor é lido **uma única vez**, na inicialização do worker/sessão (não recarrega
  no meio de uma chamada em andamento) — trocar o arquivo exige reiniciar a
  chamada/app pra valer.
- Implementação de referência: `jarvis/nucleo/preferencias.py`, função
  `interrupcao_ativa() -> bool`. Lê o arquivo relativo à raiz do projeto (nunca um
  caminho fixo pra uma máquina específica), navega `config[0]["interrupcao"]`
  exatamente nesse formato, e devolve `False` com um aviso no console pra qualquer
  caso fora do feliz (arquivo ausente, campo ausente, JSON inválido) — nunca trava a
  inicialização do app por causa de um `config.json` ruim ou ausente.

### As três checagens de `self.alfred_falando` em `enviar_microfone`

`self.alfred_falando` é a flag central: `True` enquanto o jarvis está
falando/tocando áudio, `False` quando o microfone pode ser usado. Existem TRÊS
pontos separados, todos dentro do método que captura e envia o áudio do microfone
pro Gemini, que checam essa flag pra decidir se descartam o áudio capturado —
existem três porque o áudio passa por três estágios diferentes antes de sair pro
Gemini, e cada estágio precisa da sua própria guarda:

1. **No callback síncrono do `sounddevice`** (a função chamada automaticamente toda
   vez que um novo bloco de áudio é capturado do hardware do microfone) — primeira
   linha de defesa, descarta o bloco antes de qualquer processamento.
2. **Na função que efetivamente põe o bloco na fila assíncrona** (chamada via
   `loop.call_soon_threadsafe` a partir do callback acima, já que o callback do
   sounddevice roda fora do loop `asyncio`) — segunda checagem, porque entre o
   callback disparar e essa função rodar no loop `asyncio`, `alfred_falando` pode
   ter mudado de `False` pra `True`.
3. **No loop consumidor que tira blocos da fila e chama
   `sessao.send_realtime_input(audio=...)`** — terceira e última checagem, logo
   antes de mandar de fato pro Gemini, porque um bloco pode ter entrado na fila
   poucos milissegundos antes de o jarvis começar a falar.

No comportamento padrão (`interrupcao: false`), as três são exatamente `if
self.alfred_falando: <descarta o bloco>`. Pra habilitar o modo de interrupção, cada
uma das três vira `if self.alfred_falando and not <flag de interrupção habilitada>:
<descarta o bloco>` — ou seja, só descarta quando a interrupção está desligada. Com
a flag ligada, o áudio do microfone passa a ser sempre capturado e enviado,
independente de `alfred_falando`. Mantenha as duas versões como um `if` simples no
início de cada checagem — não duplique o método inteiro pra isso.

### Tratamento do sinal de interrupção do servidor

Quando o usuário fala por cima e o servidor decide que isso conta como uma
interrupção real, a resposta que chega no loop que recebe as respostas da sessão
(equivalente a `receber_audio` neste projeto) traz um campo booleano avisando disso
— confirmado no SDK oficial (`google.genai`) instalado durante esta implementação:
a classe da resposta (`LiveServerContent`, acessível como
`resposta.server_content` no fluxo deste projeto) tem um campo `interrupted:
Optional[bool]`, com a descrição oficial "If true, indicates that a client message
has interrupted current model generation. If the client is playing out the content
in realtime, this is a good signal to stop and empty the current queue." — ou seja,
`resposta.server_content.interrupted`. Não assuma esse nome de campo sem confirmar
contra o SDK/doc oficial instalados no momento — nomes de campo da Live API já
mudaram de comportamento entre versões de modelo neste mesmo projeto (ver a nota
sobre `send_client_content` vs `send_realtime_input` na seção `chat_jarvis` do
CLAUDE.md).

Ao detectar `interrupted == True` (só quando o modo de interrupção está habilitado
— no modo padrão isso não deveria disparar de verdade, já que o microfone nem
chega a ser enviado enquanto o jarvis fala), o cliente precisa, na hora:

1. **Esvaziar a fila de áudio de saída** (a fila entre "recebeu da sessão" e "está
   tocando nos alto-falantes", equivalente a `fila_saida` neste projeto) — sem isso,
   o áudio antigo da resposta interrompida continua tocando até o fim mesmo depois
   da interrupção, em vez de parar na hora. Mesma técnica já usada pra limpar a fila
   de microfone (`limpar_fila_microfone`): um loop de `get_nowait()` até
   `QueueEmpty`.
2. **Zerar a flag equivalente a `alfred_falando` imediatamente, sem esperar o
   atraso normal de reabertura do microfone** (`ATRASO_REABRIR_MICROFONE`/
   `liberar_microfone_apos_fala` neste projeto — um `asyncio.sleep` proposital antes
   de reabrir o microfone, pra evitar reabrir cedo demais e captar o fim da própria
   fala do assistente). No caso de interrupção, esse atraso não faz sentido: a
   própria interrupção já É o sinal de que o usuário está falando agora, então zerar
   a flag na hora (e cancelar a tarefa de reabertura atrasada, se houver uma
   pendente) é o comportamento certo.

### Risco de eco sem fone de ouvido (limitação aceita, não um bug)

Com `interrupcao: true`, o microfone capta o ambiente continuamente, inclusive
enquanto os alto-falantes do computador estão tocando a resposta do jarvis. Sem
fone de ouvido, é fisicamente possível o microfone captar o próprio áudio de saída
como se fosse o usuário falando (eco/feedback acústico), potencialmente causando uma
interrupção falsa ou uma resposta confusa. Isso é uma limitação conhecida e aceita
deste modo simples (o projeto não implementa cancelamento de eco/AEC) — não é algo a
"corrigir" numa reimplementação futura, a menos que isso mude de decisão
explicitamente.

## navegador_jarvis — sem wiring extra, de propósito (contraste com discord_jarvis e rede_jarvis)

Controle real de navegador por voz (`abrir_site`, `tocar_musica_youtube`,
`pausar_musica`, `retomar_musica`) via Playwright, API **assíncrona**
(`playwright.async_api`) — nunca a síncrona, ver CLAUDE.md pro porquê (os objetos da
API síncrona ficam presos à thread do SO que os criou, o que quebraria uma sessão
persistente reaproveitada por chamadas `despachar()` sucessivas, já que o pool padrão
de `asyncio.to_thread` pode escalar cada chamada pra uma thread diferente).

Segue o contrato padrão (`obter_function_declarations()`/`despachar()`) e **não**
precisa de nenhum wiring extra em `jarvis/gemini/cliente_live.py` além de import +
`PACOTES_REGISTRADOS` — nenhuma chamada tipo `iniciar_navegador_jarvis()` no
`__init__` do worker. Isso é diferente de propósito de `discord_jarvis`/`rede_jarvis`
(que sobem a própria thread/loop de fundo eagerly, no `__init__`, pra já estarem
prontos antes de qualquer chamada de voz) — `jarvis/pacotes/navegador_jarvis/sessao.py` usa o MESMO
padrão de thread dedicada + loop próprio + `run_coroutine_threadsafe` como ponte
(idêntico ao `jarvis/pacotes/discord_jarvis/cliente.py`), mas sobe essa thread de forma **preguiçosa**
(`_garantir_thread()`, chamada de dentro de cada ação), na primeira vez que alguma
ação de navegador é pedida de verdade — não faz sentido abrir um processo Chromium
antes de qualquer pedido, ao contrário de uma conexão de rede/bot que já faz sentido
manter viva o tempo todo. Se um pacote futuro precisar da mesma técnica de "thread +
loop dedicados sob demanda", este é o exemplo a seguir — `discord_jarvis` continua
sendo o exemplo certo pra "sempre ligado desde o `__init__`".

A sessão (`browser`/`context`/`page`) é module-level state dentro da thread dedicada,
reaproveitada entre chamadas — nunca reaberta a cada ação — e se autorrecupera
sozinha se a página/navegador cair (usuário fechou a janela na mão, processo
travou): antes de cada ação, `_obter_pagina_async()` confere `pagina.is_closed()` e
reabre do zero se precisar, sem erro nenhum surgindo por causa disso sozinho.

## Cérebro reserva (assume quando o Gemini falha)

`jarvis/pacotes/cerebro_reserva/` conduz a conversa por voz quando a sessão
Live morre. **Não é um pacote de tools** (`obter_function_declarations()`
devolve `[]`, `despachar()` devolve `None`, não entra em
`PACOTES_REGISTRADOS`) — mesmo caso de `ativacao_voz` e `explorador_windows`.

Um turno seu é: `escuta.ouvir()` (microfone → WAV → Groq Whisper) →
`cerebro.responder()` (Mistral, com ferramentas) → `fala.falar()` (voz SAPI do
Windows). Medido de ponta a ponta: **3,0s por turno** quando usa ferramenta,
~1,9s em conversa simples.

**Ele herda as ferramentas sozinho.** `esquema.py` converte as
`FunctionDeclaration` que cada pacote já expõe (formato Gemini) para o formato
de `tools` da API estilo OpenAI. Ou seja: um pacote novo que entre em
`PACOTES_REGISTRADOS` passa a funcionar no modo reserva **sem tocar em nada
deste pacote**. As descrições originais são reaproveitadas na íntegra, nunca
reescritas — as regras de segurança delas ("nunca escolha sozinho", "pergunte
antes") ficam entre 68% e 95% do texto, então uma segunda cópia resumida
perderia exatamente as salvaguardas.

As tools **nativas** (memória, print, foto, encerrar) são a exceção: elas são
declaradas dentro de `executar()`, como variável local, e não dá para
reaproveitá-las de fora. As poucas que fazem sentido estão redeclaradas em
`ferramentas_locais.py`, chamando os mesmos serviços de `jarvis/servicos/`.
`preparar_email`/`confirmar_envio_email` ficaram **de fora de propósito**: o
envio de email é uma confirmação em duas etapas garantida por código, com o
rascunho pendente guardado no worker, e recriar isso aqui seria um segundo
caminho capaz de disparar um envio.

### Wiring no cliente

Cinco pontos de contato em `jarvis/gemini/cliente_live.py`:

```python
# 1. Import (junto dos outros imports de pacote)
from jarvis.pacotes import cerebro_reserva

# 2. Estado, no __init__ do worker
self.encerrou_por_falha = False
self.reserva_ativa = False

# 3. Em CADA ponto que encerra a chamada por FALHA (não por pedido do
#    usuário), antes do self.ativo = False:
self.encerrou_por_falha = True

# 4. parar() precisa encerrar o modo reserva também, senão o botão de
#    encerrar não tem efeito depois da troca:
def parar(self):
    self.ativo = False
    self.reserva_ativa = False

# 5. No fim de executar(), ANTES de ativacao_voz.retomar() — assim a
#    chamada só termina de verdade (e só aí run() emite
#    chamada_encerrada) depois que o modo reserva acabar:
if self.encerrou_por_falha and cerebro_reserva.esta_disponivel():
    self.reserva_ativa = True

    try:
        await asyncio.to_thread(
            cerebro_reserva.assumir,
            PACOTES_REGISTRADOS,
            lambda: self.reserva_ativa,
            self.status_recebido.emit,
        )

    finally:
        self.reserva_ativa = False
```

`assumir()` é síncrona e bloqueante (grava microfone, chama APIs, fala), por
isso vai em `asyncio.to_thread`. `PACOTES_REGISTRADOS` é passado **por
parâmetro**: o pacote nunca importa `cliente_live.py`, que seria import
circular.

A troca é silenciosa por decisão explícita do usuário — a instrução de sistema
do modo reserva proíbe mencionar falha, troca de sistema ou qual modelo está
respondendo.

## memoria_obsidian (substitui a memória em JSON)

`jarvis/pacotes/memoria_obsidian/` guarda a memória do jarvis como notas `.md`
ligadas por `[[links]]` numa pasta dedicada (`PASTA_VAULT_JARVIS`). O app do
Obsidian não precisa estar instalado nem aberto — são arquivos de texto comuns.

É um **pacote de tools normal**: expõe `salvar_memoria`,
`buscar_memorias_relacionadas`, `esquecer_memoria` e `listar_memorias` pelo
contrato padrão. Por isso o `cliente_live.py` ficou MENOR ao adotá-lo: as três
`FunctionDeclaration` nativas de memória e os três ramos de despacho saíram de
lá. O cérebro reserva também herdou essas tools de graça, sem wiring nenhum.

### Wiring no cliente

Além do import + `PACOTES_REGISTRADOS`, só uma coisa a mais: o contexto
inicial da sessão deixou de ser "toda a memória" e virou "as poucas notas mais
recentes".

```python
# Em vez de contexto_memorias() do gerenciador antigo:
memorias_atuais = await asyncio.to_thread(
    memoria_obsidian.contexto_inicial
)
```

E, uma vez na inicialização do app (`main.py`), a manutenção periódica:

```python
memoria_obsidian.iniciar()   # dispara a varredura em thread de fundo
```

`iniciar()` é idempotente e não bloqueia: só arquiva/consolida se já fizer mais
de `INTERVALO_VARREDURA_DIAS` desde a última vez (registrado em
`dados/memoria_obsidian_controle.json`).

### O ciclo de vida de uma nota

```
ativa  ->  arquivada  ->  resumida (e só então o original é apagado)
```

Nenhuma etapa é pulada. Uma nota só é arquivada se os **três** critérios
baterem juntos: `last_used` há mais de 90 dias **E** `access_count` < 2 **E**
`pinned == false`. Arquivar é **mover** para `arquivo/`, nunca apagar. Um
original só some depois de ter entrado num resumo **gravado com sucesso em
disco** — se a chamada de resumo falhar, nada é apagado (confirmado ao vivo:
um 404 e um 503 reais durante os testes deixaram as 16 notas intactas).

Uma nota do `arquivo/` citada numa busca é **reativada**: volta para a pasta
ativa com `access_count` zerado.

### Migração

Passo manual, roda uma vez:

```
python -m jarvis.pacotes.memoria_obsidian.migracao
```

Lê `dados/memoria.json`, cria uma nota por memória preservando o texto e a data
de criação originais, e **não apaga nem altera o JSON antigo**.

## Seleção de microfone e alto-falante (config.json)

`jarvis/ui/painel_dispositivos.py` põe dois selects na tela inicial. **Não é um
pacote de tools** — é UI mais uma preferência local, guardada no `config.json`
junto de `interrupcao` e `prioridade_alta`:

```json
{ "config": [ { "microfone": "Microfone (HyperX ...)", "alto_falante": "..." } ] }
```

Guarda-se o **nome** do aparelho, nunca o índice: índice muda quando qualquer
dispositivo é conectado ou removido.

Para religar em outro cliente, dois pontos:

```python
# 1. main.py, antes de qualquer stream ser aberto:
from jarvis.ui.painel_dispositivos import aplicar_preferencias
aplicar_preferencias()

# 2. Na janela: instanciar e posicionar
self.painel_dispositivos = PainelDispositivos()
layout.addWidget(self.painel_dispositivos)
```

A escolha é aplicada em `sd.default.device`, então **todos** os streams do
projeto passam a usá-la sem nenhuma alteração: microfone da chamada,
reprodução, detector de palavra-chave e a escuta do cérebro reserva.

## Prompts centralizados (jarvis/nucleo/prompts/)

Todo texto de instrução hardcoded enviado a algum modelo (Gemini, Groq,
Cerebras, OpenAI, Mistral), de qualquer pacote, mora em
`jarvis/nucleo/prompts/` — constantes curtas em `prompts/__init__.py`
(organizadas por seção/pacote de origem), e os dois prompts realmente
grandes (a instrução de sistema completa do Gemini Live e o bloco de
autenticação) em arquivos `.md` dentro da mesma pasta.

Um pacote que precisa de um texto de instrução importa:

```python
from jarvis.nucleo import prompts

texto = prompts.NOME_DA_CONSTANTE.format(campo=valor)
```

Ao adicionar um pacote novo com prompt próprio: se for curto (poucas frases),
vira constante em `prompts/__init__.py`, numa seção nova comentada com o
nome do pacote. Só crie um `.md` separado se o prompt for realmente
grande/multi-seção, como os dois que já existem — nesse caso, ao editar,
re-verifique o texto montado (a função de carregamento normaliza espaços
entre linhas, mas ainda vale reler o resultado final antes de considerar
pronto).
## Checklist para religar tudo em um cliente novo

1. Copie o trecho da seção "Trecho pronto para copiar" (imports,
   `PACOTES_REGISTRADOS`, extensão de `tools`, loop de despacho).
2. Para cada pacote listado na seção "Wiring extra por pacote" acima,
   copie também o wiring específico dele.
3. Rode o app e confirme que `PACOTES_REGISTRADOS` aparece com todos
   os pacotes esperados e que uma tool de cada pacote funciona por
   voz.
