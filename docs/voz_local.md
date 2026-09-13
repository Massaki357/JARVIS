# jarvis/cerebro/voz_local/ — terceiro cérebro de voz (servidor local)

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> ⚠️ **ESTE ARQUIVO FOI RECONSTRUÍDO, NÃO EXTRAÍDO.** Os outros 30 documentos desta
> pasta foram gerados automaticamente a partir do CLAUDE.md raiz, mas o gerador tinha
> um off-by-one: escreveu `conteúdo[i]` no `nome[i+1]`, então o primeiro nome
> (`abrir_aplicativo.md`) nunca foi criado e o último conteúdo — este — nunca foi
> escrito. Quando o erro foi descoberto (07/09/2026), a seção original já não existia
> em lugar nenhum verificável: os 30 arquivos nunca foram commitados, nenhum commit do
> CLAUDE.md contém a string `voz_local` (a versão do HEAD é anterior ao terceiro
> cérebro), não havia stash nem backup em disco, e os transcripts de sessão em
> `~/.claude/projects/` só guardavam fragmentos.
>
> **Fonte desta reconstrução:** o CLAUDE.md completo, como estava carregado no contexto
> da sessão de 07/09/2026 — fiel, mas **não conferido byte a byte contra o arquivo
> original**, ao contrário dos outros 30. O conteúdo abaixo é confiável para entender
> as decisões de design e as restrições; se precisar de **precisão absoluta** sobre um
> valor, nome de constante ou assinatura, confira contra o código em
> `jarvis/cerebro/voz_local/` e contra a seção "Terceiro cérebro de voz" do
> `docs/INTEGRATION.md` (esse sim versionado e íntegro), que cobre boa parte do mesmo
> material pelo ângulo do contrato de integração.

## Arquitetura e decisões de design

Fala com o **alfred-server**, um servidor de voz rodando em Docker nesta máquina, pelo
broker MQTT dele (mosquitto). Mesmo ponto único de troca dos outros workers:
`_classe_do_worker()` em `jarvis/ui/janela_principal.py` (agora um `if` de três vias
lendo `provedor_ativo()`), e a mesma API pública no worker, então nada mais na UI mudou.

### Protocolo — DUAS etapas, com a decisão de roteamento no meio

O servidor dividiu o pipeline dele exatamente para o cliente poder decidir, olhando o
TEXTO, se a fala era uma ferramenta ou uma conversa:

| Etapa | Tópico de entrada | Tópico de saída | Payload |
|---|---|---|---|
| 1 — transcrição | `jarvis/audio/entrada` | `jarvis/texto/saida` | arquivo de áudio inteiro cru na entrada; JSON UTF-8 `{"texto","tom","sexo"}` na saída |
| 2 — resposta falada | `jarvis/texto/entrada` | `jarvis/audio/saida` | o MESMO JSON de volta na entrada; o WAV da resposta na saída |

`jarvis/audio/erro` é **um** tópico para as duas metades — não existe
`jarvis/texto/erro`. O servidor prefixa a linha com a metade que falhou
(`"transcrição: ..."` / `"resposta: ..."`), e é isso que identifica a requisição. Os
cinco nomes, mais host/porta/credenciais e os dois timeouts, são sobrescrevíveis por
`.env` via `jarvis/cerebro/voz_local/config.py` (que tem `config_schema()` e está
registrado em `configuracoes/pacotes.py`).

### O turno, de ponta a ponta

`_capturar_frase` (VAD) → `_transcrever` (etapa 1) → `_rotear` → se `usou_ferramenta`
ou `pedido_esclarecimento`, o turno termina localmente e **a etapa 2 nunca é chamada**;
senão `_pedir_resposta` (etapa 2) → `_reproduzir_resposta`.

A etapa 2 republica o **dict JSON inteiro** recebido da etapa 1 em vez de remontá-lo
campo a campo — é literalmente o que o servidor espera de volta, e preserva `tom`/`sexo`
exatamente como ele os produziu.

### Ferramentas funcionam neste modo, via `jarvis/roteamento_hierarquico`

O mesmo motor, chamado com o texto transcrito e `self.transcricao_conversa` como
histórico (ele já usa o formato `{"role","content"}`). `processar_turno` **executa a
ferramenta ele mesmo**, então `_rotear` só lê a decisão; não há dispatch aqui. É
síncrono e faz HTTP mais o despacho da ferramenta, então sempre vai por
`asyncio.to_thread`. Um turno de ferramenta produz **fala nenhuma** — o texto do
resultado vai para a UI por `status_recebido` e entra no histórico. Uma falha de
roteamento nunca custa o turno: degrada para o ramo de conversa e reporta. Sem
`GROQ_API_KEY` o roteamento não roda e **todo** turno vira conversa — o worker avisa
por `erro_recebido` logo depois de conectar, em vez de perder toda ferramenta em
silêncio.

`pedido_esclarecimento` fica deliberadamente agrupado com o ramo de ferramenta, não com
o de conversa: o roteamento entendeu que uma ação era desejada, mas não qual. Mandar o
texto original para a etapa 2 faria o servidor conversar sobre um pedido que ele não
faz ideia que existe.

### Memória no modo local: o cliente monta e envia a cada chamada

`jarvis/cerebro/voz_local/contexto.py`. Os cérebros baseados em sessão resolvem isso uma
vez na conexão — uma instrução de sistema (prompt do perfil + `contexto_inicial()` +
data/hora) no `LiveConnectConfig`/`session.update`, e daí a própria sessão segura o
histórico, e o que faltar o modelo busca com a ferramenta
`buscar_memorias_relacionadas`. **Nada disso vale para um servidor de requisição por
turno**: não há sessão para segurar histórico, e o servidor não consegue chamar uma
ferramenta porque não sabe que memória existe. Então a divisão é a mesma já escolhida
para as ferramentas — o cliente monta o contexto, o servidor só usa o que recebe e não
guarda nada.

Dois campos **opcionais** foram somados ao payload da etapa 2: `historico` (só turnos
anteriores, `{"role","content"}`, limitado a `LIMITE_MENSAGENS_HISTORICO` = 6, nunca
incluindo a fala atual, que já vai em `texto`) e `contexto_sistema` (identidade +
data/hora + fatos relevantes, limitado a 1200 chars). Eles já são enviados, antes de o
servidor suportá-los: `_tratar_texto` lê o payload chave a chave com `.get`, então
campos desconhecidos são ignorados e nada quebra — a fiação simplesmente começa a
funcionar no dia em que o servidor entregar a metade dele.

Os fatos vêm do mesmo motor que a ferramenta do Gemini usa,
`memoria_obsidian.busca.buscar_memorias`, com duas escolhas deliberadas.
`registrar=False`: contar um acesso manteria `last_used` permanentemente fresco e
impediria os critérios de poda de disparar — o mesmo raciocínio já documentado para
`contexto_inicial()`. E `PONTUACAO_MINIMA = 2.0`, medido contra o vault real: a busca
pontua um acerto genuíno em 4.0 e uma nota que só encostou no assunto em 1.0, então sem
o corte "qual é o meu nome" também arrastava notas de navegador e YouTube — ruído que
come o orçamento de contexto e convida o modelo a falar do que ninguém perguntou. A
seção `## Relacionados` também é removida (navegação do Obsidian, não fato). Uma falha
ao ler o vault degrada para um contexto sem fatos e nunca custa o turno.

### O histórico é unilateral até o servidor devolver o texto dele

`/responder` hoje responde só com o WAV, então as falas do assistente não entram em
`transcricao_conversa` — entram os turnos do usuário e os resultados de ferramenta. Para
o caso relatado isso basta (o usuário foi quem disse o nome), mas o assistente não
consegue se referir ao que acabou de dizer. Fechar isso exige o servidor devolver também
o texto gerado: como user property MQTT em `jarvis/audio/saida` (metadado ao lado de um
payload binário é exatamente o padrão de `rede_jarvis/mqtt_client.py`) ou como header
HTTP codificado. Não implementado em nenhum dos dois lados; pertence ao prompt do lado
do servidor.

### As 16 tools nativas do Gemini não existem neste modo, por design

Elas são ramos `elif` dentro de `processar_chamada_de_funcao`, não pacotes — ausentes de
`roteamento_hierarquico/catalogo.py` e sem código de pacote por trás, então `_despachar`
nunca as encontraria: `analisar_tela`, `analisar_camera`,
`iniciar_visualizacao_continua`, `parar_visualizacao_continua`, `salvar_print_tela`,
`tirar_foto_camera`, `enviar_captura_email`, `enviar_captura_discord_dm`,
`enviar_captura_discord_canal`, `enviar_captura_remoto`, `preparar_email`,
`confirmar_envio_email`, `ler_emails`, `baixar_anexo_email`, `encerrar_chamada`,
`pausar_chamada`.

As quatro de visão ao vivo são impossíveis por natureza (elas empurram o frame *para
dentro* da sessão via `send_realtime_input(video=...)`, e o servidor só troca áudio); as
de email e captura são Python puro e seriam portáveis para um pacote, só nunca foram.
**Consequências práticas**: "olha minha tela"/"vê a câmera" é recusado por design, não
por bug, e a ausência de `encerrar_chamada` significa que uma chamada em modo local só
pode ser encerrada pelo botão. A visão que *funciona* aqui vem do catálogo:
`identificar_planta`, `consultar_segunda_opiniao_visual`, `abrir_camera`/`fechar_camera`,
e `clicar_elemento_visual` (que captura sozinho).

`analisar_tela` e `analisar_camera` foram **PORTADAS** para o catálogo genérico como
`jarvis/pacotes/descricao_visual/` (`descrever_tela`, `descrever_camera`): o cliente
captura, um modelo de visão devolve uma descrição em **texto**, e esse texto entra no
turno como resultado de ferramenta comum. **Os nomes diferem das nativas de propósito** —
o dispatch do worker do Gemini percorre `PACOTES_REGISTRADOS` *antes* da cadeia `elif`
nativa, então um pacote registrado com nome de nativa sequestraria o comportamento
próprio do Gemini (que transmite vídeo real para dentro da sessão); um teste agora impede
que qualquer pacote use `analisar_tela`/`analisar_camera`. `descrever_tela` usa
`capturar_monitor_do_cursor_bytes` (o monitor do cursor, igual à nativa) e
`descrever_camera` usa `capturar_camera_bytes`; ambas são marcadas **sensíveis** em
`perfis/sensiveis.py`, como as nativas que substituem.

`iniciar_visualizacao_continua`/`parar_visualizacao_continua` continuam indisponíveis por
design, e **não** são o mesmo problema das duas portadas: elas precisam de streaming de
vídeo em tempo real, enquanto a portagem é "uma captura, uma descrição". Replicá-las com
chamadas de visão repetidas seria uma funcionalidade diferente, com custo e latência
muito piores. Deliberadamente não implementado.

### O gancho `preparar_argumentos`

`identificar_planta` e `consultar_segunda_opiniao_visual` precisam de uma imagem que só o
cliente pode produzir — no worker do Gemini o cliente injeta `imagem_bytes` em `args`
antes do despacho. Ambas eram alcançáveis pelo roteamento aqui e falhavam **toda vez**
com "nenhuma imagem foi capturada", porque nada fornecia a imagem. Corrigido com um
gancho `preparar_argumentos` em `processar_turno`: o `_preparar_argumentos_da_ferramenta`
do worker captura exatamente para os nomes em `FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM` e
devolve uma **cópia** dos args. Essa constante é um **dict de nome → `"tela"`/`"camera"`**
(quatro entradas agora, já que as duas portadas usam o mesmo mecanismo); a função de
captura é resolvida em tempo de chamada por `_CAPTURAS` em vez de guardada no mapa, o que
a mantém substituível em teste. O gancho foi escolhido em vez de deixar os pacotes
capturarem sozinhos, o que teria mudado o comportamento deles também no caminho do
Gemini, onde o cliente captura sob `_mutex_funcao_visual` de propósito. Nenhum mutex é
necessário aqui: este worker é estritamente sequencial, e `capturar_camera_bytes` já
compartilha o handle com a janela de preview.

### O VAD classifica cada bloco por CONTEÚDO (Silero), não por amplitude

Isso substituiu um bug real e relatado. O `_capturar_frase()` original decidia
fala-versus-silêncio com `calcular_nivel_audio()` (pico normalizado) contra `LIMIAR_VOZ`.
Isso é um medidor de volume, e volume não distingue fala de outra coisa: com ruído de
fundo alto e contínuo — uma moto passando, um ventilador, música tocando — **todo** bloco
fica acima do limiar, `silencio_acumulado` nunca cresce, e a fala nunca fecha; o microfone
segue gravando enquanto o ruído durar. Medido aqui no padrão 0.12: ruído branco forte e um
zumbido de motor de 90 Hz foram classificados como fala em **100%** dos blocos.
`jarvis/cerebro/voz_local/vad_silero.py` agora responde essa pergunta com o Silero VAD, e
`config.LIMIAR_PROB_FALA` (0.5) é uma **probabilidade**, não um nível. Mesmos sinais: 0,0%
(ruído branco, música), 4,3% (ventilador), 13,0% (motor), contra 74,0% em fala real.

**O que NÃO mudou**: tudo sobre *quanto tempo* de não-fala encerra a frase.
`SILENCIO_SEGUNDOS`, `BLOCOS_PRE_FALA`, `BLOCOS_POS_FALA`, `DURACAO_MINIMA_SEGUNDOS`
(ainda medida só sobre `duracao_com_voz`) e `DURACAO_MAXIMA_SEGUNDOS` estão intocados — só
a classificação por bloco mudou. `calcular_nivel_audio()` também continua exatamente como
era: ainda anima a esfera, o que genuinamente *é* um medidor de volume, e ainda alimenta o
modo de emergência.

**onnxruntime, NÃO o pacote `silero-vad` do PyPI, e isso é deliberado.** Aquele pacote
declara `torch` e `torchaudio` como dependências duras e o `__init__.py` dele importa
torch mesmo no caminho ONNX (`import torch` no topo de `utils_vad.py`, que `model.py`
importa) — confirmado instalando e vendo o import falhar sem torch. São ~250 MB de
dependência, num projeto sem nenhum outro uso de torch, para rodar um modelo de 1,2 MB. O
`requirements.txt` recebe `onnxruntime` (~15 MB) sozinho.

**O contrato do modelo foi lido do wrapper oficial (`OnnxWrapper.__call__`), não chutado, e
tem duas armadilhas.** A janela é de **exatamente 512 amostras** a 16 kHz, e cada chamada
precisa receber **576**: as últimas 64 amostras da janela anterior (o "contexto") na frente
das 512 atuais. Sem esse contexto o modelo devolve ~0.001 para **tudo**, fala real
inclusive — que foi o primeiro resultado aqui, e parece modelo quebrado em vez de entrada
malformada. O modelo também é **recorrente** (um estado `(2,1,128)` carregado entre
janelas), e é por isso que `DetectorDeFala.zerar()` existe e é chamado no começo de toda
frase.

Custo por bloco medido, não presumido: 0,21–0,26 ms para classificar um bloco de 64 ms —
cerca de **250–300× mais rápido que tempo real**. Um teste garante que fique abaixo de um
décimo da duração do bloco.

O modelo é baixado no primeiro uso e cacheado em `dados/modelos/` (gitignored), do mesmo
jeito que o `ativacao_voz` trata o modelo do Vosk. Ordem de resolução:
`VOZ_LOCAL_MODELO_VAD` → o cache → uma cópia dentro de um pacote `silero-vad` instalado
(achado por caminho, nunca importado, para torch nunca ser tocado) → download de uma **tag
fixada** (`v6.2.1`; `master` deixaria o modelo mudar sob o projeto sem mudança de código).
O download escreve num arquivo `.parcial` e renomeia, então um download interrompido não
deixa um `.onnx` truncado no cache.

**Falhar ao carregar o VAD nunca custa a chamada.** `_preparar_detector_de_fala()` reporta
por `erro_recebido` (a UI, não só o console) e deixa `self.detector_fala = None`, e o
`_bloco_tem_fala()` cai no critério antigo de amplitude. Esse fallback *é* o bug descrito
acima, e está documentado como modo de emergência de propósito — um VAD pior é melhor que
não conseguir falar com o assistente.

Detalhes do VAD ajustados contra uma falha real, não chutados: `BLOCOS_PRE_FALA` (5) blocos
são guardados de *antes* do limiar ser cruzado, porque quando o nível sobe a primeira
sílaba já foi; o silêncio final que fechou a fala é aparado para `BLOCOS_POS_FALA` (5) para
todo arquivo publicado não carregar um `SILENCIO_SEGUNDOS` inteiro de nada. **A guarda de
duração mínima mede só os blocos com voz (`duracao_com_voz`), nunca o buffer** — medir o
buffer fazia um clique de 0,1s com 1s de silêncio atrás parecer uma fala de 1,4s e chegar
ao servidor; pego por um teste, corrigido no código, não no teste.

**Limite conhecido, medido**: ruído de banda larga com SNR genuinamente ruim (ruído branco
em RMS 0,25 sobre a fala) derruba a detecção de fala para ~0%. Ruído harmônico — motores,
ventiladores, música, que é o que foi relatado — não faz isso: fala sobre um motor de 90 Hz
ainda lê 92,3%.

### Interrupção de fala (barge-in) FUNCIONA no modo local, com detecção no cliente

O oposto dos outros dois cérebros. No Gemini Live o **servidor** decide: o microfone segue
sendo transmitido enquanto o assistente fala, e o servidor responde com
`server_content.interrupted`. Aqui o `alfred-server` já entregou o WAV inteiro e não sabe
mais nada do turno, então `_vigiar_interrupcao()` roda ao lado da reprodução e reusa o
**mesmo detector Silero** que fecha as falas. Ao detectar: a reprodução para no meio da
palavra, o resto do WAV é descartado, o `ATRASO_REABRIR_MICROFONE` é pulado (o usuário está
falando *agora* — esse atraso seria latência pura), a fila do microfone **não** é limpa, e
os blocos que o vigia já havia consumido são carregados para o `_capturar_frase` seguinte
como pre-roll dele. Sem esse carregamento as primeiras sílabas da interrupção se perdem,
porque o vigia as tirou da fila e ninguém mais as veria.

**Exige FONE DE OUVIDO, e isso é medido, não precaução.** Não há cancelamento de eco
acústico em lugar nenhum deste projeto, e o Silero decide por **conteúdo** — a voz do
assistente é fala humana. Alimentado com WAVs de resposta reais deste servidor, o detector
viu fala em **68%–82%** dos blocos; atenuado a **−24 dB** (eco de alto-falante distante)
ainda viu **67%–81%**, porque fala baixa continua sendo fala. Então em alto-falante o
assistente se interrompe em quase toda resposta — e, ao contrário do VAD antigo por
amplitude, subir um limiar não resolve. Um teste garante isso diretamente (a própria voz do
assistente a −12 dB *interrompe*), então o comportamento fica fixado em vez de ser
descoberto depois.

Opt-in pela preferência que já existe: `config.json` → `"interrupcao"`, lida uma vez no
`__init__` por `preferencias.interrupcao_ativa()` — a mesma flag do worker do Gemini,
deliberadamente não um segundo botão. Padrão desligado. Não tem entrada na tela de
configurações porque aquela tela cobre variáveis de `.env` e esta mora no `config.json`;
em vez disso o worker emite um aviso de uma linha na UI no começo de toda chamada quando
está ligada, que é onde ele de fato é lido.

Dois amortecedores contra disparo falso, ambos necessários:
`BLOCOS_FALA_PARA_INTERROMPER` (5 blocos consecutivos de fala, ~320 ms — um bloco isolado é
clique de teclado ou respiração) e `CARENCIA_INTERRUPCAO_SEGUNDOS` (0,5 s no começo da
reprodução, durante os quais os blocos ainda são bufferizados para pre-roll mas nunca
contam como interrupção — o rabo da própria pergunta do usuário ainda está no ar quando a
resposta começa).

`self.interrupcoes_na_chamada` + uma linha de log `[INTERRUPÇÃO]` existem pelo mesmo motivo
do contador do worker do Gemini: uma interrupção **falsa** é indistinguível de um
travamento para quem está ouvindo — a frase para e nunca retoma. Se esse número sobe
enquanto o usuário está calado, a causa é barge-in e a correção é `config.json`, não código.

As duas guardas de microfone locais carregam a exceção canônica
`and not self.interrupcao_habilitada`, exatamente como as três do worker do Gemini. São
duas aqui, não três, porque este worker não tem laço de envio — o microfone alimenta o
`_capturar_frase`, não uma sessão. Um teste as conta.

**Interromper durante a GERAÇÃO (antes da reprodução começar) deliberadamente não foi
implementado.** O protocolo do servidor não tem canal de cancelamento — cinco tópicos,
nenhum de controle — e o pipeline dele é síncrono, então honrar um cancelamento exigiria
mudar os dois lados. O comportamento escolhido é: deixar a geração terminar e descartá-la
na chegada, o que não custa nada para implementar porque `_resolver_futuro` já descarta
respostas que chegam sem futuro pendente.

### Por que este worker não pôde ser copiado dos outros dois

É estrutural. Gemini Live e OpenAI Realtime são sessões de *streaming* bidirecional onde o
**servidor** decide onde o turno do usuário terminou. O alfred-server é requisição/resposta
com **arquivos inteiros**. Então este worker tem que (1) decidir sozinho onde a fala
termina — `_capturar_frase()` roda o VAD — e (2) conversar em turnos estritamente
sequenciais (captura → publica → espera → toca → captura), sem tarefas paralelas de
envio/recepção.

### Respostas atrasadas são casadas por etapa, não só por pendência

`self._tipo_esperado` (`"texto"` ou `"audio"`) controla o `_resolver_futuro`: os dois pares
de tópicos são independentes, então um WAV atrasado do turno anterior pode chegar enquanto
a etapa 1 espera, e sem a checagem de tipo ele seria devolvido como se fosse o JSON da
transcrição. Erros resolvem qualquer uma das etapas, já que o servidor publica as duas
metades num tópico só.

### Um segundo cliente MQTT no projeto é inevitável

Não é descuido de duplicação. O `jarvis/pacotes/rede_jarvis/mqtt_client.py` mantém um
cliente por processo (`obter_cliente()`) apontado para o broker de nuvem do rede_jarvis
(HiveMQ, porta 8883), chama `tls_set()` incondicionalmente, e define usuário/senha mais um
Last Will de presença. Um objeto cliente do paho é uma conexão para **um** endereço — não
pode também servir `localhost:1884` sem TLS. O `jarvis/cerebro/voz_local/mqtt_voz.py`
repete a *forma* daquele arquivo (paho v2, MQTT5, callbacks em português, nunca levantando
para fora) numa conexão separada, e o `rede_jarvis` está intocado byte a byte. Ao contrário
daquele, aqui não há singleton: cada chamada cria e desconecta a própria instância.

### Um caractere de controle na user property `texto` DERRUBA o servidor

Bug real, encontrado ao vivo, corrigido no `alfred-server`. Strings UTF-8 do MQTT v5 não
podem conter caracteres de controle, e o mosquitto impõe isso matando a conexão:
`bad socket read/write: Malformed UTF-8`. Como o paho reconecta sozinho, um publish ruim
vira um laço infinito de conectar/assinar/cair, o `alfred-server` some do broker, e todo o
modo de voz local fica morto até o container ser reiniciado — com `/health` reportando
`"mqtt": false` e nada mais obviamente errado. O gatilho é banal: a LLM respondeu com uma
**quebra de linha** (qualquer resposta de duas frases pode). Reproduzido isolado depois —
`\n`, `\r` e `\t` cada um derruba a conexão; caracteres acentuados nunca, então não é
problema de encoding. O `alfred-server/api/main.py::_texto_para_property` agora mapeia todo
caractere de controle (U+0000–U+001F e U+007F–U+009F) para espaço, colapsa sequências de
espaço em branco, e trunca em `LIMITE_TEXTO_PROPERTY_BYTES` (4096) **em bytes**, decodificando
com `errors="ignore"` para o corte não partir um caractere multibyte e produzir exatamente o
UTF-8 malformado que ele existe para evitar. Não relaxe essa sanitização, e não adicione um
segundo lugar que defina user property sem ela. O lado do JARVIS não define property nenhuma
ao publicar, então não consegue disparar isso — a correção pertence ao servidor.

### Uma FALHA de roteamento nunca pode ser tratada como conversa

Bug real, relatado como "pedi para abrir o navegador, ele disse que estava abrindo e nada
abriu; na segunda vez funcionou". Causa medida ao vivo: o tier gratuito da Groq limita o
`openai/gpt-oss-20b` a **8000 tokens por minuto**, cada chamada da etapa 1 custa **~1450
tokens** (o catálogo inteiro de 45 ferramentas viaja no prompt todo turno), então qualquer
coisa mais rápida que ~5 turnos/minuto toma 429. O `_chamar_groq` (hoje substituído por `jarvis/servicos/agentes/`, `erros.py` + `PoliticaRepeticao`) devolvia `(False, ...)` em
vez de levantar, o `processar_turno` transformava isso num `ResultadoTurno` comum com
`usou_ferramenta=False`, e o worker — que só capturava *exceções* — mandava a fala para a
etapa 2. O servidor local não faz ideia de que ferramentas existem, então respondeu algo
plausível ("claro, abrindo o navegador") enquanto nada rodou, e o erro da Groq foi
descartado inteiro.

Três correções: `ResultadoTurno.falhou` (marcado em todo ponto de falha genuíno — chave
ausente, etapa 1 falhou, schemas não carregáveis, etapa 2 falhou, ferramenta não
reconhecida, gancho levantou — mas **não** para `pedido_esclarecimento`, que é um resultado
real); o worker reporta `falhou` por `erro_recebido` e encerra o turno sem chamar a etapa 2;
e o `_chamar_groq` agora refaz **só** no 429 (`TENTATIVAS_RATE_LIMIT`, honrando o
`retry-after`, limitado por `ESPERA_MAXIMA_RATE_LIMIT`) e preserva o corpo da resposta, de
modo que um rate limit recuperável deixa de ser indistinguível de qualquer outro erro HTTP.
A falha não pode ser *falada*: a única saída de voz é a etapa 2, que responde ao texto que
recebe em vez de lê-lo, então mandar o erro para lá faria o servidor conversar sobre o erro.

### O 400 da Groq `Tool choice is none, but model called a tool`

Falha real relatada, e o recurso de histórico foi o que a expôs. A etapa 1 declara
**nenhuma ferramenta** (é o ponto inteiro do roteador de duas etapas: o catálogo viaja como
*texto*, não como ~45 schemas), então `tool_choice` é implicitamente `none`. O
`openai/gpt-oss-20b` mesmo assim decide, às vezes, *chamar* a ferramenta em vez de escrever
o nome dela na linha `FERRAMENTAS:`, e a Groq então rejeita a **requisição inteira** com um
400. O usuário bateu nisso em "salve na sua memória que gosto de conversar sobre
tecnologia", logo depois de uma pergunta que o assistente já havia respondido.

**É não determinístico e depende do histórico, medido**: com a frase exata e nenhum turno
anterior, **0 falhas em 8**; com um turno `assistant` anterior no histórico, **1 a 3 falhas
a cada 6** chamadas idênticas. É por isso que só começou a aparecer quando as respostas do
assistente passaram a entrar em `transcricao_conversa` — o recurso não criou a fragilidade,
só começou a encontrá-la.

**Mexer no texto do prompt não resolve — foi testado, e piorou.** Somar um "você não tem
ferramentas nesta etapa, nunca emita uma tool call" explícito deu 3 falhas em 6 contra 1 em
6 sem ele. O canal de ferramenta do formato harmony não é algo que uma instrução desliga.
Não "resolva" isso reescrevendo `ROTEAMENTO_ETAPA1_INSTRUCAO`.

**Trocar de modelo também não é solução**: `qwen/qwen3.6-27b` rejeita o prompt do catálogo
de saída (`Request too large` — o limite por requisição dele é menor que o que a etapa 1
precisa), e o `openai/gpt-oss-120b` é da mesma família harmony. Os modelos de chat Llama que
a Groq servia sumiram do catálogo inteiramente.

**A correção tem duas camadas, ambas no `roteador.py`.** (1) O `_chamar_groq` agora refaz
esse **um** 400 específico — a única exceção à regra vigente de "nunca refazer um 4xx",
justificada porque a resposta não é função só da requisição — com orçamento próprio
(`TENTATIVAS_TOOL_CALL_INDEVIDA`, **2**) mantido **independente** do orçamento do 429, e
**sem sleep** (não é rate limit). (2) Se a etapa 1 ainda falhar assim *e* houver histórico,
o `processar_turno` a refaz uma vez **sem o histórico**, o que remove o gatilho medido em vez
de só rolar o dado de novo. Perder contexto conversacional numa nova tentativa é uma troca
deliberada contra perder o turno inteiro, que é o que o usuário de fato via.

**Medido antes e depois, ao vivo, no turno exato relatado**: 1 falha em 5 só com o retry (um
turno esgotou as tentativas), **0 em 5** com o fallback de histórico somado. **O orçamento de
retry é pequeno de propósito (2), e isso é uma decisão de orçamento de tokens**: cada
tentativa da etapa 1 custa ~1,8k tokens contra os 8000 TPM do tier gratuito, então refazer à
vontade só troca o 400 pelo 429 — observado uma vez, numa corrida posterior com orçamento 3,
onde o único turno que falhou morreu de rate limit em vez de na tool call. O fallback de
histórico é ao mesmo tempo a correção efetiva e a chamada mais barata (ele tira o histórico do
prompt), então ele carrega o peso e o retry cego fica como uma primeira linha fina.

O teto de TPM em si foi deliberadamente deixado em paz (decisão do dono): espera-se que o
retry absorva a maior parte. Se os rate limits continuarem perceptíveis apesar do retry, as
opções são encurtar o catálogo ou sair do tier gratuito — o catálogo de ~1359 tokens em todo
prompt da etapa 1 é o motor do custo.

### Todo caminho de falha foi construído para não travar o app

Reusando as proteções já provadas no `cliente_live.py`: um broker morto devolve
`(False, mensagem)` antes de o microfone sequer abrir; um erro em `jarvis/audio/erro` e um
timeout de resposta (`VOZ_LOCAL_TIMEOUT_RESPOSTA_SEGUNDOS`) ambos aparecem por
`erro_recebido` e **voltam a escutar** em vez de encerrar a chamada; uma resposta que chega
depois do timeout é **descartada** no `_resolver_futuro` (o futuro do turno já é `None`) para
não tocar por cima do turno seguinte — a mesma guarda também absorve uma mensagem retida no
broker; `_vigiar_microfone()` pega um stream de entrada que silenciosamente para de entregar
blocos (o timestamp é carimbado como **primeira** instrução do callback, acima de todo return
antecipado, pelo mesmo motivo do worker do Gemini); as três tarefas de chamada passam por
`_tarefa_supervisionada`; e a escrita no dispositivo de saída é envolvida em
`asyncio.wait_for` num executor **dedicado** de um worker, nunca `asyncio.to_thread`.

### DOIS BROKERS MQTT NESTA MÁQUINA — a causa de um diagnóstico errado

Vale saber antes de depurar qualquer coisa de MQTT aqui. Uma sessão anterior reportou que o
`alfred-api` "não estava conectado ao broker", com base em publicar em `localhost:1883` e não
ver resposta, mais o `$SYS/broker/clients/connected` reportando 1. Essa conclusão estava
**errada**, e o motivo é estrutural: `Get-NetTCPConnection -LocalPort 1883` mostra um
**`mosquitto.exe` nativo do Windows** ligado a `127.0.0.1` e `::1`, enquanto o Docker publica
no coringa `::`. No Windows o bind de endereço específico ganha do coringa, e `localhost`
resolve para `::1`/`127.0.0.1` — então **toda conexão a `localhost:1883` a partir do host cai
no broker nativo**, um broker vazio sem alfred-server nenhum. A leitura do `$SYS` era
literalmente verdadeira para *aquele* broker. O servidor estava certo o tempo todo: o log do
próprio mosquitto mostra `alfred-server` conectado de `172.24.0.3`, assinando
`jarvis/audio/entrada` QoS 1, com PING a cada 60s, nunca desconectado.

**A correção escolhida pelo dono: remapear a porta publicada do container.** O
`alfred-server/docker-compose.yml` agora publica o broker como `"1884:1883"`, e o
`VOZ_LOCAL_MQTT_PORT` tem default **1884**. Nada mudou dentro da rede do compose (a API
continua falando com `mosquitto:1883`) e o broker nativo do Windows foi deixado rodando e
intocado. **Se o MQTT aqui parecer silenciosamente morto de novo, confira com qual broker você
está falando antes de qualquer outra coisa** — `$SYS/broker/clients/connected` mais um grep do
seu próprio client id em `docker logs alfred-mosquitto` resolvem em segundos. Note também que o
broker do rede_jarvis não tem relação: é HiveMQ Cloud na 8883, não este mosquitto nativo.

### O que este modo NÃO tem — inerente ao protocolo do servidor, não pendência

O servidor não faz function calling (as ferramentas vêm do motor de roteamento, sobre o texto
transcrito), e não há perfis, prompt de sistema nem porta de autenticação por palavra-chave —
esses pertencem à sessão Gemini/OpenAI, que não existe aqui; não há retomada de sessão
(`solicitou_reconexao`/`session_handle_atualizado` existem só por paridade de interface e nunca
são emitidos, igual ao worker da OpenAI).
`solicitar_analise_tela`/`solicitar_analise_camera`/`enviar_texto_da_ui`/`enviar_imagem_da_ui`
existem porque a janela os chama sem saber qual cérebro está ativo, e eles **recusam com
explicação** por `erro_recebido` (devolvendo `False` onde se espera um bool) em vez de
silenciosamente não fazer nada — o servidor só aceita áudio, então não há canal para uma imagem
nem para texto digitado.

### Verificação

104 verificações automatizadas em `testes/testar_voz_local.py` (hoje 297, com o crescimento
posterior da suíte), offline exceto a parte 5, que conversa com o mosquitto **real** em tópicos
`jarvis/teste/...` sem encostar no pipeline do alfred-server: paridade de API entre os três
workers, resolução de `PROVEDOR_IA` (um erro de digitação de fato cai para o Gemini), conversão
PCM/WAV (taxa lida do header, estéreo, WAV inválido, 8-bit rejeitado), o VAD em quatro casos,
transporte MQTT real para os três tópicos assinados (payloads chegam byte a byte idênticos,
texto de erro acentuado decodificado, publish grande demais recusado, broker morto falha rápido
e por escrito), as duas etapas de um turno independentemente (a etapa 1 nunca dispara a etapa 2;
a etapa 2 republica o dict sem alterar), um erro do servidor e um timeout em **cada** etapa com
o limite próprio dela, um WAV atrasado chegando enquanto a etapa 1 espera texto sendo descartado
em vez de aceito, JSON malformado da etapa 1 virando erro de turno, o ramo de roteamento
(ferramenta versus conversa, histórico sem a fala atual, falha degradando para conversa, poda do
histórico), as recusas explícitas, e que o caminho do Gemini está intocado.

**Estado da verificação ponta a ponta (atualizado em 07/09/2026):** o fluxo de duas etapas
**já completou contra o servidor real**. O `testes/testar_voz_local_ponta_a_ponta.py` roda com o
container no ar: transcrição em 1,6s (`jarvis/audio/entrada` → `jarvis/texto/saida`), o
roteamento decidiu conversa, e a resposta falada voltou em 21,6s (`jarvis/texto/entrada` →
`jarvis/audio/saida`) como um WAV válido de 24 kHz e 2,92s. O log do container confirma
`MQTT assinando jarvis/audio/entrada e jarvis/texto/entrada`, ou seja, as duas metades.
*(Nota histórica: até o rebuild da imagem, o `GET /openapi.json` do `alfred-api` expunha só
`/health` e `/processar`, e publicar áudio era respondido em `jarvis/audio/saida` de uma vez só,
sem nada em `jarvis/texto/saida` — o código de duas etapas existia no `alfred-server/api/main.py`
mas a imagem em execução era anterior a ele. Essa pendência está resolvida.)*

## Restrições a preservar ao editar

- **`VOZ_LOCAL_MQTT_PORT` tem default 1884, não 1883, e isso é estrutural nesta máquina** — um
  `mosquitto.exe` nativo do Windows é dono de `127.0.0.1:1883`/`::1:1883` e ganha do bind coringa
  do Docker, então `localhost:1883` alcança um broker vazio. Antes de concluir que algo de MQTT
  "não responde" aqui, confirme com qual broker você está falando
  (`$SYS/broker/clients/connected`, mais um grep do seu client id em
  `docker logs alfred-mosquitto`).
- **`jarvis/cerebro/voz_local/` deve manter o cliente paho próprio — nunca roteie por
  `jarvis/pacotes/rede_jarvis/mqtt_client.py`.** São brokers diferentes (nuvem + TLS + auth +
  Last Will de presença contra `localhost:1884` puro), e um objeto cliente do paho é uma conexão
  para um endereço. Não "deduplique" os dois generalizando o `obter_cliente()` numa fábrica: isso
  edita código que funciona e carrega credenciais sem ganho funcional, e o `rede_jarvis` deve
  ficar byte a byte intocado por este recurso.
- **O VAD do cérebro local deve continuar classificando blocos por CONTEÚDO (Silero), nunca
  voltar para amplitude.** `LIMIAR_VOZ` e `calcular_nivel_audio()` continuam existindo — o
  primeiro para o fallback de emergência, o segundo porque a animação da esfera genuinamente é um
  medidor de volume —, mas nenhum dos dois pode voltar a decidir fala-versus-silêncio no
  `_capturar_frase`. Amplitude não distingue fala de ruído, que é exatamente o bug relatado: com
  ruído de fundo alto e contínuo todo bloco lê como fala, `silencio_acumulado` nunca cresce e a
  fala nunca fecha. Um teste garante as duas direções, então reverter quebra a suíte em vez de
  aparecer depois como um microfone que não solta.
- **Não "simplifique" o `vad_silero.py` trocando pelo pacote `silero-vad` do PyPI.** Ele exige
  torch+torchaudio (~250 MB) e importa torch mesmo no caminho ONNX, para um modelo de 1,2 MB. E
  não remova o contexto de 64 amostras posto na frente de cada janela de 512, nem o `zerar()` por
  frase: sem o contexto o modelo devolve ~0.001 para tudo, fala inclusive, e sem o reset o rabo de
  uma frase enviesa o começo da seguinte.
- **A checagem de duração mínima do VAD local deve continuar medindo `duracao_com_voz` (só os
  blocos com voz), nunca o tamanho do buffer capturado.** O buffer carrega `BLOCOS_PRE_FALA` de
  entrada e o silêncio que fechou a fala, então medi-lo torna um clique de 0,1s indistinguível de
  uma frase real e o manda para o servidor. Do mesmo modo, mantenha o pre-roll (cortá-lo come a
  primeira sílaba) e mantenha o aparo do silêncio final.
- **Barge-in no cérebro local deve continuar opt-in e manter os dois amortecedores.** A exceção
  `and not self.interrupcao_habilitada` pertence a **ambas** as guardas de microfone (um teste
  conta 2); `BLOCOS_FALA_PARA_INTERROMPER` e `CARENCIA_INTERRUPCAO_SEGUNDOS` são o que impedem um
  clique de teclado ou o rabo da própria pergunta do usuário de cortar a resposta. No caminho de
  interrupção, nunca restaure o sleep de `ATRASO_REABRIR_MICROFONE` nem a chamada
  `limpar_fila_microfone` — o primeiro é latência pura enquanto o usuário já está falando, e a
  segunda come o começo da frase que ele acabou de iniciar. E nunca descarte o carregamento de
  `_blocos_apos_interrupcao` para o pre-roll do `_capturar_frase`: o vigia consumiu aqueles blocos
  da fila, então nada mais consegue recuperá-los. Não amarre a um botão novo tampouco —
  `config.json` → `"interrupcao"` é deliberadamente compartilhado com o worker do Gemini.
- **Um turno de ferramenta no cérebro local nunca pode chamar a etapa 2.** A razão inteira de o
  servidor ter dividido o pipeline é a decisão de roteamento caber entre as metades; chamar
  `jarvis/texto/entrada` depois de uma ferramenta já ter rodado faria o servidor conversar sobre
  um pedido que ele nunca viu. Mantenha `pedido_esclarecimento` nesse mesmo ramo, e mantenha a
  chamada de roteamento indo por `asyncio.to_thread` — `processar_turno` faz HTTP mais o despacho
  da ferramenta e travaria o loop.
- **`_resolver_futuro` deve continuar casando a resposta contra `self._tipo_esperado`.** Só
  pendência não basta: os dois pares de tópicos são independentes, então um WAV atrasado do turno
  anterior pode chegar enquanto a etapa 1 espera JSON, e sem a checagem de tipo ele seria devolvido
  como se fosse a transcrição. Erros são a exceção deliberada — resolvem qualquer etapa que esteja
  esperando, porque o servidor publica os erros das duas metades num tópico só.
- **`ResultadoTurno.falhou` deve continuar sendo checado antes do ramo ferramenta/conversa, e nunca
  ser confundido com `usou_ferramenta=False`.** Eles são idênticos de outro modo, e tratar um
  roteamento que falhou como conversa é exatamente o que fez o assistente afirmar que tinha aberto
  o navegador enquanto nada rodou. `pedido_esclarecimento` deliberadamente NÃO é uma falha.
- **A política de repetição do roteamento (`_POLITICA` em `roteamento_hierarquico/roteador.py`, aplicada por `jarvis/servicos/agentes/agente.executar` com a classificação de `erros.py`) refaz exatamente duas coisas e nada mais: um 429, e o 400 específico
  `Tool choice is none, but model called a tool`.** O segundo é o único retry de 4xx sancionado no
  projeto — existe porque aquela resposta varia entre requisições byte a byte idênticas, o que não
  vale para um 401 ou um corpo malformado — e mantém orçamento próprio para que um rate limit não
  o consuma. Não amplie para 4xx em geral, não funda os dois orçamentos, e não adicione sleep a ele.
  Mantenha o fallback da etapa 1 que refaz **sem o histórico** como último recurso: o histórico é o
  gatilho medido, então removê-lo é melhor que rolar o dado de novo. E não tente resolver nada disso
  editando `ROTEAMENTO_ETAPA1_INSTRUCAO` — o texto do prompt foi testado contra isso e piorou.
- **A classificação de erro (`jarvis/servicos/agentes/erros.py`) deve continuar preservando o motivo real e o `retry-after` de um erro** (`descrever`, `cabecalho`, `espera_sugerida`). Descartá-los é o que
  fez um rate limit recuperável parecer uma falha HTTP genérica, custando uma sessão inteira de
  engenharia reversa para diagnosticar. O `retry-after` que o servidor manda é autoritativo, mas
  deve continuar limitado — é um valor vindo de fora do processo.
- **O gancho `preparar_argumentos` é como um cliente fornece dado que só ele pode produzir** (hoje
  o frame de câmera para `identificar_planta` / `consultar_segunda_opiniao_visual`). Não
  "simplifique" isso fazendo os pacotes capturarem sozinhos: eles também são despachados pelo
  worker do Gemini, que captura sob `_mutex_funcao_visual` de propósito, e um pacote que captura
  sozinho passaria por cima disso.
- **Uma falha de turno no cérebro local nunca pode encerrar a chamada.** Um erro em
  `jarvis/audio/erro`, uma falha de publish e um timeout de resposta todos aparecem por
  `erro_recebido` e voltam a escutar — só falha de conexão, de microfone ou de tarefa encerra a
  chamada. E `_resolver_futuro` deve continuar descartando áudio que chega sem futuro pendente:
  essa única guarda é o que impede uma resposta atrasada (ou uma mensagem retida no broker) de
  tocar por cima do turno seguinte.
- **`_classe_do_worker()` em `jarvis/ui/janela_principal.py` continua sendo o único lugar do projeto
  que escolhe um cérebro de voz**, e os três workers devem continuar expondo a API pública idêntica
  (os sete sinais, o construtor
  `(session_handle, transcricao_inicial, ativado_por_voz, slug_perfil)`, `parar`,
  `solicitar_analise_tela`, `solicitar_analise_camera`, `enviar_texto_da_ui`,
  `enviar_imagem_da_ui`, `transcricao_conversa`, `slug_perfil`). Um método que a janela chame em só
  um deles quebra a troca. As recusas do worker local devem continuar explícitas
  (`erro_recebido` + `False`), nunca no-ops silenciosos.
