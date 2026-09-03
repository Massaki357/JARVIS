# ARQUITETURA DO PROJETO — ALFRED

Este documento descreve **o que cada arquivo do projeto faz**, função por função quando relevante. Ele é o mapa detalhado do código; para uma visão de mais alto nível (fluxo entre camadas, decisões de design) veja o `CLAUDE.md`. Para instruções de instalação e uso, veja o `README.MD`.

O projeto está organizado em seis pastas: `ui/`, `gemini/`, `actions/`, `vision/`, `memory/` e `core/`, mais o `main.py` na raiz.

```
JARVIS/
├── main.py
├── core/
│   └── config.py
├── gemini/
│   └── live_client.py
├── ui/
│   ├── main_window.py
│   └── alfred_visualizer.py
├── actions/
│   ├── file_actions.py
│   ├── app_actions.py
│   ├── browser_actions.py
│   ├── web_search.py
│   ├── mouse_actions.py
│   ├── text_actions.py
│   └── agenda_actions.py
├── vision/
│   ├── screen_capture.py
│   ├── camera_capture.py
│   └── click_locator.py
└── memory/
    ├── memory_manager.py
    ├── memory.json      (criado em tempo de execução)
    └── agenda.json
```

---

## `main.py`

Ponto de entrada da aplicação.

- Instala um filtro de mensagens do Qt (`qInstallMessageHandler`) que esconde apenas o aviso conhecido `"SetProcessDpiAwarenessContext() failed"` no Windows, deixando todos os outros avisos/erros visíveis no terminal.
- Cria o `QApplication`, instancia `MainWindow` (de `ui/main_window.py`), exibe a janela e entra no loop de eventos do Qt (`app.exec()`).
- Substitui o antigo `main_basic.py` da versão inicial do curso.

---

## `core/config.py`

Carrega a configuração do projeto a partir do `.env` (via `python-dotenv`) e expõe três constantes usadas em todo o projeto:

- `GEMINI_API_KEY` — chave de API lida de `.env`.
- `GEMINI_LIVE_MODEL` — modelo usado na sessão de voz em tempo real (atualmente `"gemini-3.1-flash-live-preview"`). Outras opções testadas ficam comentadas logo abaixo, para facilitar a troca.
- `GEMINI_VOICE` — voz usada pelo ALFRED (atualmente `"Charon"`). A lista completa de vozes disponíveis está comentada no arquivo.

`vision/click_locator.py` também lê sua própria variável de ambiente opcional (`GEMINI_VISION_MODEL`) diretamente com `os.getenv`, sem passar por este módulo.

---

## `ui/main_window.py`

Classe `MainWindow(QMainWindow)` — a janela principal da interface "futurista" do ALFRED (troca o antigo `main_window_basic.py`).

**Layout:** dois painéis lado a lado dentro de um `QHBoxLayout`:
- **Painel lateral** (`painelLateral`, largura fixa 280px): título "SYSTEM CORE", subtítulo, botão principal de chamada (`btn_chamada`), botão "ANALISAR TELA" (`btn_tela`), botão "ANALISAR CÂMERA" (`btn_camera`) e uma caixa de log somente leitura (`log_box`, "EVENT STREAM") que registra cada evento da sessão.
- **Painel principal** (`painelPrincipal`): contém o `AlfredVisualizer` (a esfera animada — ver `ui/alfred_visualizer.py`).

Todo o visual é definido por uma folha de estilo QSS embutida na constante `ESTILO_GLOBAL` (tema escuro/vermelho).

**Estado e ciclo de vida da chamada:**
- `self.live_worker` — instância atual de `GeminiLiveWorker` (`None` quando não há chamada ativa).
- `self.session_handle` — token de retomada de sessão do Gemini Live, preservado entre reconexões automáticas (não é apagado quando o servidor pede renovação via `GoAway`, mas **é** apagado em qualquer encerramento manual ou por voz, para que a próxima chamada comece limpa).
- `self.reconectar_automaticamente` / `self.encerramento_manual` — flags que distinguem uma queda de conexão (deve reconectar sozinho, preservando a conversa) de um encerramento pedido pelo usuário ou por comando de voz (não deve reconectar).

**Métodos principais:**
- `alternar_chamada()` — alterna entre `iniciar_chamada()` e `encerrar_chamada()` conforme exista ou não um worker ativo.
- `iniciar_chamada()` — cria um novo `GeminiLiveWorker(session_handle=self.session_handle)`, conecta todos os sinais Qt do worker (`status_recebido`, `erro_recebido`, `chamada_encerrada`, `solicitou_encerramento`, `solicitou_reconexao`, `session_handle_atualizado`, `nivel_audio`) aos métodos correspondentes da janela, e inicia a thread (`.start()`).
- `encerrar_chamada()` / `encerrar_chamada_por_voz()` — encerram a chamada; a versão por voz também limpa o `session_handle` (chamada pelo sinal `solicitou_encerramento`, emitido quando o usuário pede para desligar por voz).
- `atualizar_status(texto)` — repassa mensagens de status ao `AlfredVisualizer` (`definir_status`) e ao log.
- `mostrar_erro(erro)` — marca `reconectar_automaticamente = True` (se o encerramento não foi manual) e atualiza a UI.
- `chamada_finalizada()` — chamado quando a `QThread` termina; restaura os botões, zera o visualizador e, se `reconectar_automaticamente` estiver ativo, agenda uma nova chamada com `QTimer.singleShot(450, self.iniciar_chamada)` — reconectando automaticamente sem perder o contexto da conversa.
- `preparar_reconexao_automatica()` — conectado a `solicitou_reconexao`; trata o aviso `GoAway` do servidor Gemini (renovação normal de WebSocket) como uma reconexão esperada, não como erro.
- `salvar_session_handle(handle)` — guarda o token mais recente de retomada de sessão emitido pelo worker.
- `analisar_tela()` / `analisar_camera()` — acionados pelos botões; chamam `live_worker.solicitar_analise_tela()` / `solicitar_analise_camera()` (captura e envio manual de imagem, independente das tools de voz).
- `closeEvent(event)` — ao fechar a janela, para a thread do worker e aguarda até 3s pelo encerramento limpo.

---

## `ui/alfred_visualizer.py`

Classe `AlfredVisualizer(QWidget)` — **arquivo inteiramente novo**. É o painel visual animado (uma esfera/orbe futurista) que reage ao estado da chamada e ao volume da voz do ALFRED. Desenho feito manualmente com `QPainter` (gradientes lineares/radiais, sem QML nem shaders).

**Otimização de desempenho:** o fundo (`_criar_fundo_cache`) e a esfera (`_criar_esfera_cache`) são pesados para desenhar, então são renderizados uma única vez em `QPixmap` (cache) quando o widget é criado ou redimensionado (`resizeEvent` → `_recriar_cache`). A cada quadro, o `paintEvent` só desenha por cima do cache os elementos que realmente mudam:
- `_desenhar_brilho_reativo` — brilho que pulsa com o áudio/estado.
- `_desenhar_aneis` — dois anéis giratórios.
- `_desenhar_indicador_audio` — barra/onda reativa ao nível de voz.
- `_desenhar_textos` — status textual (ex.: "CONECTANDO", "OFFLINE").

**FPS adaptativo** (`_definir_fps`, via `QTimer`): `FPS_OFFLINE = 6`, `FPS_ATIVO = 15`, `FPS_FALANDO = 20` — a animação roda mais devagar quando ocioso para economizar CPU, e acelera automaticamente quando há voz ativa (`definir_nivel_audio` sobe o FPS quando `nivel_audio > 0.04`).

**API pública usada pela `MainWindow`:**
- `definir_status(texto)` — atualiza o texto exibido (convertido para maiúsculas).
- `definir_ativo(ativo)` — liga/desliga o modo "conectado" (muda FPS e zera o áudio ao desativar).
- `definir_nivel_audio(nivel)` — recebe o valor de 0.0 a 1.0 emitido pelo sinal `nivel_audio` do `GeminiLiveWorker` a cada bloco de áudio reproduzido; o valor é suavizado (`nivel_suavizado`) para evitar movimentos bruscos na animação.

---

## `gemini/live_client.py`

O núcleo da aplicação. Classe `GeminiLiveWorker(QThread)` — substitui e expande enormemente o antigo `live_client_basic.py`. Roda em thread própria com seu próprio loop `asyncio` (`run()` → `asyncio.run(self.executar())`), mantendo a UI responsiva.

### Sinais Qt emitidos para a interface

| Sinal | Quando é emitido |
|---|---|
| `status_recebido(str)` | mensagens de status (conectando, executando ação X, etc.) |
| `erro_recebido(str)` | erros da sessão |
| `chamada_encerrada()` | a thread terminou |
| `nivel_audio(float)` | nível de volume (0–1) a cada bloco de áudio reproduzido, para animar a esfera |
| `solicitou_encerramento()` | o usuário pediu para encerrar por voz (tool `encerrar_chamada`) |
| `solicitou_reconexao()` | o servidor pediu renovação do WebSocket (`GoAway`) — não é erro |
| `session_handle_atualizado(str)` | novo token de retomada de sessão, para preservar contexto entre reconexões |

### `executar()` — configuração da sessão

Monta a lista de `tools` (`types.Tool` com uma `FunctionDeclaration` por função), a `instrucao_sistema` (system prompt) e o `LiveConnectConfig`, então abre `client.aio.live.connect(...)`. Usa `session_resumption` (preserva contexto em reconexões) e `context_window_compression` (evita corte por limite de contexto). Depois inicia três tasks assíncronas concorrentes, como na versão básica:
- `enviar_microfone` — mic → Gemini.
- `receber_audio` — Gemini → fila de reprodução + despacho de tool calls.
- `reproduzir_audio` — fila → alto-falantes.

Se qualquer uma dessas tasks falhar ou terminar inesperadamente, a sessão inteira é derrubada (`RuntimeError`) em vez de continuar "viva" silenciosamente.

### Gate de autenticação por voz (preservado)

A `instrucao_sistema` continua começando pela mesma trava de segurança da versão básica: só interage após o usuário dizer a palavra-chave **"Coisa"**, nunca revela a palavra-chave, tolera no máximo três erros antes de bloquear o acesso na chamada, e não repete "Acesso autorizado" sem uma nova fala do usuário. **Este gate não deve ser removido ou enfraquecido em refatorações.**

### Ferramentas (tools) disponíveis para o Gemini chamar por voz

Cada uma é declarada em `tools` e tratada em `processar_chamada_de_funcao` (despacho por `if/elif` no nome da função). A tabela lista o nome da tool, os parâmetros que o modelo deve enviar, e a função Python real que ela executa:

| Tool | Parâmetros | Executa |
|---|---|---|
| `analisar_tela` | — | `vision.screen_capture.capturar_tela_bytes` (via `processar_funcao_visual`) |
| `analisar_camera` | — | `vision.camera_capture.capturar_camera_bytes` (via `processar_funcao_visual`) |
| `criar_pasta_area_trabalho` | `nome` | `actions.file_actions.criar_pasta_area_trabalho` |
| `listar_area_de_trabalho` | — | `actions.file_actions.listar_area_de_trabalho` |
| `organizar_area_de_trabalho_basico` | — | `actions.file_actions.organizar_area_de_trabalho_basico` |
| `copiar_item_area_trabalho` | `nome`, `pasta_origem` | `actions.file_actions.copiar_item_area_trabalho` |
| `recortar_item_area_trabalho` | `nome`, `pasta_origem` | `actions.file_actions.recortar_item_area_trabalho` |
| `colar_item_area_trabalho` | `pasta_destino` | `actions.file_actions.colar_item_area_trabalho` |
| `renomear_item_area_trabalho` | `nome_atual`, `novo_nome`, `pasta_origem` | `actions.file_actions.renomear_item_area_trabalho` |
| `cancelar_transferencia_area_trabalho` | — | `actions.file_actions.cancelar_transferencia_area_trabalho` |
| `criar_evento_agenda` | `titulo`, `data_hora` (`YYYY-MM-DD HH:MM`) | `actions.agenda_actions.criar_evento_agenda` |
| `listar_agenda` | — | `actions.agenda_actions.listar_agenda` |
| `cancelar_evento_agenda` | `referencia` (id ou trecho do título) | `actions.agenda_actions.cancelar_evento_agenda` |
| `abrir_aplicativo` | `nome` | `actions.app_actions.abrir_aplicativo` |
| `pesquisar_no_navegador` | `consulta` | `actions.browser_actions.pesquisar_no_navegador` |
| `pesquisar_informacao_atual` | `consulta` | `actions.web_search.avaliar_necessidade_pesquisa` decide primeiro se vale a pena; só então chama `actions.web_search.pesquisar_informacao_atual` (senão devolve `resposta_sem_pesquisa`) |
| `tocar_no_youtube` | `busca` | `actions.browser_actions.tocar_no_youtube` |
| `escrever_no_campo_ativo` | `texto` | `actions.text_actions.escrever_no_campo_ativo` (áudio silenciado até o fim do turno) |
| `rolar_pagina` | `direcao`, `quantidade` | `actions.mouse_actions.rolar_pagina` (áudio silenciado até o fim do turno) |
| `clicar_mouse` | — | `actions.mouse_actions.clicar_mouse` |
| `duplo_clique_mouse` | — | `actions.mouse_actions.duplo_clique_mouse` |
| `clique_direito_mouse` | — | `actions.mouse_actions.clique_direito_mouse` |
| `clicar_elemento_visual` | `alvo` (descrição do elemento) | `vision.click_locator.localizar_elemento_na_tela` (localiza via IA visual) seguido de `actions.mouse_actions.mover_e_clicar` (áudio silenciado até o fim do turno) |
| `salvar_memoria` | `texto` | `memory.memory_manager.salvar_memoria` |
| `listar_memorias` | — | `memory.memory_manager.listar_memorias` |
| `esquecer_memoria` | `referencia` (id ou trecho) | `memory.memory_manager.esquecer_memoria` |
| `encerrar_chamada` | — | marca `encerrar_depois = True`; a chamada é encerrada de fato ~2.8s depois via `encerrar_apos_resposta()`, dando tempo para a despedida terminar de tocar |

Todas as chamadas de função "locais" (não visuais) passam por `executar_funcao_local(funcao, *args, timeout=15)`, que roda a função síncrona em thread separada (`asyncio.to_thread`) com timeout — evita travar o loop assíncrono e devolve uma mensagem amigável em caso de timeout ou exceção.

### Visão sob demanda (throttle/cooldown)

`processar_funcao_visual` controla `analisar_tela`/`analisar_camera`: usa um mutex (`executando_funcao_visual`) para impedir chamadas simultâneas e um cooldown de `COOLDOWN_FUNCAO_VISUAL = 8.0` segundos para a mesma função, evitando que o modelo recapture a mesma imagem repetidamente para um único pedido. A imagem capturada fica em `self.imagem_visual_pendente` e só é enviada ao Gemini (`enviar_imagem_visual_pendente`) depois que a resposta da tool call é confirmada (`send_tool_response`), garantindo a ordem correta dos eventos no protocolo Live.

Os botões "ANALISAR TELA"/"ANALISAR CÂMERA" da UI usam um caminho **separado** (`solicitar_analise_tela`/`enviar_tela_para_gemini` e equivalentes de câmera), que envia a imagem diretamente via `send_client_content` sem passar pelo mecanismo de tool call — por isso a `MainWindow` pode disparar uma análise visual mesmo sem o modelo "decidir" chamar a tool.

### Outras mudanças em relação à versão básica

- **`silenciar_audio_ate_fim_turno`** — flag nova usada por ações que devem acontecer em silêncio (rolagem de página, escrita no campo ativo, clique visual): a resposta em áudio do Gemini para aquele turno é descartada, e a flag é religada em `False` quando `turn_complete` chega.
- **Renovação de sessão (`GoAway`)** — trecho novo em `receber_audio` que detecta o aviso `go_away` do servidor, marca `renovacao_em_andamento`, emite `solicitou_reconexao` e derruba a sessão atual de forma limpa (a UI reabre automaticamente usando o `session_handle` mais recente, preservando o contexto da conversa).
- **`session_resumption_update`** — a cada resposta, verifica se o servidor enviou um novo `handle` retomável e propaga via `session_handle_atualizado`.
- **Data/hora atual** injetada na `instrucao_sistema` (`datetime.now()`) para o modelo interpretar corretamente termos como "hoje", "amanhã" e dias da semana ao criar eventos de agenda.
- **Personalidade expandida**: seções extras na `instrucao_sistema` cobrindo tom mais irônico/sarcástico, preferências musicais do usuário (rock: Linkin Park, Creed, Hoobastank), regras específicas para cada nova ferramenta (funções locais, pesquisa atual, agenda, mouse, escrita de texto) e reforço da seção de segurança ("nunca exclua/sobrescreva/formate arquivos").

---

## `actions/` (pasta inteiramente nova)

Cada arquivo é um módulo independente de automação do Windows, sem estado compartilhado entre si (exceto os "clipboards internos" descritos abaixo). Nenhuma função aqui é chamada diretamente pelo usuário — todas são disparadas pelo Gemini através das tools listadas em `gemini/live_client.py`.

### `actions/file_actions.py` — arquivos da Área de Trabalho

Todas as operações são restritas à Área de Trabalho do usuário (`area_de_trabalho()` localiza `OneDrive/Desktop`, `OneDrive/Área de Trabalho`, `Desktop` ou `Área de Trabalho` dentro de `Path.home()`). Toda validação de caminho passa por `_esta_dentro_da_area`/`_resolver_caminho_relativo`, que **rejeita qualquer caminho fora da Área de Trabalho** — proteção central de segurança do módulo.

- `criar_pasta_area_trabalho(nome)` — cria pasta nova; nunca sobrescreve (`exist_ok=False`).
- `listar_area_de_trabalho()` — lista os itens da raiz (até 50).
- `organizar_area_de_trabalho_basico()` — move arquivos soltos para `Imagens/`, `PDFs/`, `Documentos/`, `Compactados/` conforme extensão; ignora pastas e nunca sobrescreve.
- `copiar_item_area_trabalho(nome, pasta_origem="")` / `recortar_item_area_trabalho(...)` — não copiam/movem imediatamente; apenas guardam a referência do item em `_AREA_TRANSFERENCIA` (um "clipboard" interno em memória, não o clipboard real do Windows).
- `colar_item_area_trabalho(pasta_destino="")` — efetiva a cópia (`shutil.copytree`/`copy2`) ou o corte (`shutil.move`) preparado antes; nunca sobrescreve um item existente no destino; bloqueia colar uma pasta dentro dela mesma.
- `renomear_item_area_trabalho(nome_atual, novo_nome, pasta_origem="")` — preserva a extensão original se o novo nome não tiver uma; nunca sobrescreve.
- `cancelar_transferencia_area_trabalho()` — limpa `_AREA_TRANSFERENCIA`.
- Helpers internos: `limpar_nome` (remove caracteres proibidos no Windows: `\ / : * ? " < > |`), `_normalizar` (minúsculas + sem acento, para comparação), `_localizar_item` (busca exata e depois parcial única, com desambiguação quando há múltiplos resultados parecidos).

**Nenhuma função deste arquivo exclui arquivos.** Isso é reforçado tanto no código (`exist_ok=False`, checagens `destino.exists()`) quanto na `instrucao_sistema` do `live_client.py`.

### `actions/app_actions.py` — abrir aplicativos e recursos do Windows

`abrir_aplicativo(nome)` é a função pública principal e tenta, em ordem:
1. `abrir_especial(nome)` — recursos com apelidos fixos (Meu Computador, Explorador, Google/navegador, Windows Defender, Configurações, Calculadora, Relógio, CMD, PowerShell, Bloco de Notas, Paint, Painel de Controle, pastas pessoais Documentos/Downloads/Vídeos/Músicas via `abrir_pasta_usuario`/`localizar_pasta_usuario`).
2. `procurar_atalho_menu_iniciar(nome)` — busca recursiva por atalhos `.lnk`/`.url` nas pastas do Menu Iniciar (`APPDATA` e `PROGRAMDATA`), com correspondência exata prioritária sobre parcial.
3. `abrir_app_windows(nome)` — usa `listar_aplicativos_windows()` (executa `Get-StartApps` via PowerShell, convertendo a saída JSON) para achar o `AppID` e abrir via `explorer.exe shell:AppsFolder\<AppID>` — cobre apps da Microsoft Store.
4. `abrir_executavel_conhecido(nome)` — fallback final: dicionário fixo (Chrome, Edge, Word, Excel, Steam) resolvido com `shutil.which`.

`executar_comando` sempre usa `subprocess.Popen(..., shell=False)` (nunca `shell=True`) e `normalizar_texto` remove acentos/maiúsculas para comparação, igual ao padrão usado nos outros módulos de `actions/`.

### `actions/browser_actions.py` — pesquisa no navegador e YouTube

- `pesquisar_no_navegador(consulta)` — abre `https://www.google.com/search?q=...` no navegador padrão via `webbrowser.open`.
- `tocar_no_youtube(busca)` — busca `"<busca> official audio official video"` na página de resultados do YouTube (requisição HTTP direta com `urllib`, sem Selenium/Playwright/PyWhatKit), extrai o primeiro `videoId` do HTML com regex (`_extrair_video_id`) e abre diretamente `https://www.youtube.com/watch?v=<id>&autoplay=1`. Se não conseguir identificar um vídeo, cai de volta para a página de resultados normal do YouTube.

### `actions/web_search.py` — pesquisa "invisível" de informações atuais

Não abre nenhuma janela/aba; usada para o ALFRED responder por voz com dados atuais. Duas etapas:

1. **Filtro local instantâneo** — `avaliar_necessidade_pesquisa(consulta)` decide, sem chamar a internet, se a pergunta realmente precisa de dado atual, checando (nessa ordem) marcadores de atualidade (`hoje`, `agora`, `recentemente`...), assuntos dinâmicos (cotação, clima, notícias, placar de jogo, versão mais recente...), cargos que mudam (presidente, ministro, CEO...) e por fim padrões de pergunta estável ("o que é", "quem foi", "como funciona"...) que **bloqueiam** a pesquisa. Retorna um `DecisaoPesquisa(pesquisar: bool, motivo: str)`.
2. **Pesquisa real** — `pesquisar_informacao_atual(consulta)` só é executada se o filtro aprovar; usa a biblioteca `ddgs` (DuckDuckGo Search) para obter até 5 resultados, formata em texto para o modelo (`_formatar_resultados`) e mantém um cache em memória de 60s (`_ler_cache`/`_salvar_cache`, thread-safe via `threading.Lock`) para evitar repetir a mesma busca em sequência.
- `resposta_sem_pesquisa(consulta)` — mensagem devolvida ao Gemini quando ele tenta pesquisar algo que o filtro considera desnecessário, para reforçar que ele deve responder do próprio conhecimento.
- `precisa_pesquisar(consulta)` — atalho booleano equivalente a `avaliar_necessidade_pesquisa(consulta).pesquisar`.

### `actions/mouse_actions.py` — controle do mouse via API nativa do Windows

Usa `ctypes` para chamar `user32.dll` diretamente (sem `pyautogui`). `SetProcessDPIAware()` é chamado uma vez no import para evitar erro de coordenadas por escala de DPI.

- `rolar_pagina(direcao, quantidade=3)` — rolagem via `mouse_event(MOUSEEVENTF_WHEEL, ...)`; quantidade limitada entre 1 e 10.
- `clicar_mouse()` / `duplo_clique_mouse()` / `clique_direito_mouse()` — cliques na posição atual do cursor.
- `mover_e_clicar(x, y, duracao=0.35)` — valida se `(x, y)` está dentro da resolução atual (`GetSystemMetrics`), move o cursor suavemente em pequenos passos (`SetCursorPos` em loop) e clica ao chegar. Usada por `clicar_elemento_visual` em `live_client.py`, com as coordenadas vindas de `vision/click_locator.py`.

### `actions/text_actions.py` — escrever no campo ativo do Windows

`escrever_no_campo_ativo(texto)` insere texto no campo com foco atual, usando a API nativa do Windows em duas etapas (para preservar acentos e textos longos de forma mais confiável do que simular tecla por tecla):
1. Copia o texto para a área de transferência real do Windows via `GlobalAlloc`/`GlobalLock`/`SetClipboardData` (`_copiar_para_area_transferencia`, formato `CF_UNICODETEXT`).
2. Simula `Ctrl+V` via `keybd_event` (`_colar_no_campo_ativo`).

Limite de segurança de 10.000 caracteres (`_MAXIMO_CARACTERES`); tenta abrir o clipboard até 10 vezes com pequenas pausas antes de desistir.

### `actions/agenda_actions.py` — agenda local persistente

Gerencia `memory/agenda.json` (estrutura `{"versao": 1, "eventos": [...]}`), com gravação atômica (`_salvar_dados`: escreve em `agenda.tmp`, `fsync`, depois `Path.replace`) e `threading.Lock` (`_LOCK`) para concorrência segura — mesmo padrão usado em `memory/memory_manager.py`. **Este arquivo, não `memory/memory_manager.py`, é quem implementa a agenda.**

- `criar_evento_agenda(titulo, data_hora, alarme=False)` — `data_hora` aceita `"YYYY-MM-DD HH:MM"`, `"YYYY-MM-DDTHH:MM"`, `"DD/MM/YYYY HH:MM"` ou `"DD-MM-YYYY HH:MM"` (`_interpretar_data_hora`); recusa datas no passado e duplicatas exatas (mesmo título + mesma data/hora); mantém no máximo `MAXIMO_EVENTOS = 20` compromissos (os mais antigos saem quando o limite é excedido). O parâmetro `alarme` existe só por compatibilidade e não cria nenhum alarme de fato.
- `listar_agenda()` — lista apenas compromissos **futuros**, ordenados por data.
- `cancelar_evento_agenda(referencia)` — aceita o ID numérico exato ou um trecho do título; pede desambiguação quando há mais de uma correspondência parcial.
- `_criar_arquivo_se_necessario()` / `_carregar_dados()` — auto-recuperação: se `agenda.json` estiver ausente, vazio, com JSON inválido, sem ser um dicionário, ou com `eventos` que não seja uma lista, o arquivo é recriado do zero automaticamente. Também descarta silenciosamente eventos individuais malformados ao carregar.

---

## `vision/` (pasta pré-existente, um arquivo novo)

### `vision/screen_capture.py` (sem mudanças na versão completa)

`capturar_tela_bytes()` — captura o monitor principal com `mss`, converte para JPEG em memória via `Pillow` (qualidade 80) e retorna os bytes. Nunca grava nada em disco.

### `vision/camera_capture.py` (sem mudanças na versão completa)

`capturar_camera_bytes()` — abre a webcam padrão (índice 0) com `cv2.VideoCapture`, aguarda 0.8s e descarta os 10 primeiros frames para deixar a câmera ajustar foco/exposição, converte BGR→RGB e devolve JPEG em memória (qualidade 90). Nunca grava nada em disco.

### `vision/click_locator.py` — **arquivo novo**: localizador visual de elementos na tela

`localizar_elemento_na_tela(alvo)` é a função pública, usada pela tool `clicar_elemento_visual`. Fluxo:

1. Recusa alvos vazios e bloqueia por palavra-chave qualquer alvo que pareça uma ação sensível/destrutiva (`TERMOS_BLOQUEADOS`: excluir, apagar, deletar, formatar, comprar, pagar, transferir, instalar, desinstalar, "executar como administrador" etc.) — **esta lista é a principal proteção contra cliques perigosos guiados por voz** e é checada antes mesmo de capturar a tela.
2. Captura o monitor principal com `mss` (`_capturar_tela_principal`), sem gravar em disco.
3. Envia a captura + um prompt de instrução para um modelo Gemini separado (`GEMINI_VISION_MODEL`, padrão `"gemini-3.1-flash-lite"`, configurável por variável de ambiente), pedindo uma resposta JSON estruturada (`response_schema`) com `encontrado`, `x`/`y` normalizados de 0 a 1000, `confianca` (0–1) e `descricao`.
4. Recusa o resultado se `encontrado=false` ou se `confianca < CONFIANCA_MINIMA` (0.78) — evita clicar em algo incerto.
5. Converte as coordenadas normalizadas em pixels absolutos da tela (considerando o deslocamento do monitor), e retorna `{"sucesso": True, "x": ..., "y": ..., "confianca": ..., "descricao": ...}` para que `live_client.py` chame `actions.mouse_actions.mover_e_clicar(x, y)`.

---

## `memory/`

### `memory/memory_manager.py` (sem mudanças estruturais na versão completa)

Continua exatamente como descrito na versão básica: armazena `memory/memory.json` (criado sob demanda), protegido por `threading.Lock` e gravação atômica (`.tmp` + `Path.replace`). API pública: `salvar_memoria(texto)`, `listar_memorias()`, `esquecer_memoria(referencia)`, `contexto_memorias()` (injetado no início da `instrucao_sistema`). Limites: `MAXIMO_MEMORIAS = 50`, `MAXIMO_CARACTERES = 200` por memória. De-duplicação por `_normalizar_texto` (minúsculas, sem acento, sem espaços duplicados). `esquecer_memoria` resolve por ID exato → texto exato → correspondência parcial única (pede desambiguação se houver mais de uma). Recusa frases de exclusão em massa como "esquecer tudo".

### `memory/agenda.json`

Arquivo de dados (não é código) gerenciado por `actions/agenda_actions.py`. Estrutura: `{"versao": 1, "eventos": [{"id": "1", "titulo": "...", "data_hora": "YYYY-MM-DD HH:MM", "criado_em": "ISO 8601"}, ...]}`. Vazio (`"eventos": []`) em um repositório novo — populado conforme o usuário agenda compromissos.

### `memory/memory.json`

Não versionado no Git; criado automaticamente por `memory_manager.py` na primeira vez que uma memória é salva. Mesma estrutura de sempre: `{"versao": 1, "memorias": [{"id": ..., "texto": ..., "criada_em": ...}]}`.
