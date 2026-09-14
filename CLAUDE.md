## Project overview

ALFRED is a Windows desktop voice assistant built with PySide6 and the Gemini Live API (`google-genai`). It streams microphone audio to Gemini in real time, plays back the spoken response, and can call a small set of tools (screen capture, continuous screen viewing, webcam capture, persistent memory, sending/reading email, remote commands to other ALFRED instances over MQTT, smart home device control, delegating text tasks to other LLM providers, call termination) that the model triggers by voice. All conversation happens in Brazilian Portuguese, and all identifiers, comments, and UI strings in the codebase are in Portuguese — follow that convention when editing.

The finished course project (`JARVIS COMPLETO/` in the repo root) has since been adapted into this one: its nine `actions/` modules, its visual click locator, its animated sphere UI, its session resumption/reconnection, and its OpenAI Realtime provider all live here now (see the sections below). `JARVIS COMPLETO/` itself is kept as the reference copy and is not imported by anything.

**Comments are minimal, by the user's explicit decision.** Every explanatory comment and docstring was removed from the Python code (13.528 lines, with the AST of every file verified identical before and after). What remains is a single `#` line placed exactly where the code alone would hide a trap — "never do X here", usually pointing to the `docs/*.md` that explains why. **Don't add explanatory comments or docstrings back**, and don't restate what the code already says: the *why* belongs in the area's `docs/*.md`, which is read before editing (see below). A new trap marker is fine — one line, only when a plausible cleanup edit would silently break something. `[CURSO]` teaching comments no longer exist.

## Setup and running

No test suite, linter, or build system is configured in this repo.

```powershell
# Activate the venv (already present in ./venv)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

Requires a `.env` file (gitignored) in the project root with:
```
GEMINI_API_KEY=<your key>

# Optional — which voice brain to use: "gemini" (default), "openai" or "local".
# See jarvis/nucleo/config.py (PROVEDOR_IA / provedor_ativo / usar_provedor_openai
# / usar_provedor_local), jarvis/cerebro/openai_realtime/ and jarvis/cerebro/voz_local/. Any value
# outside PROVEDORES_VALIDOS falls back to Gemini, so a typo can never silently
# swap providers. OPENAI_API_KEY is the SAME key delegacao_ia already uses:
PROVEDOR_IA=<gemini (default), openai, or local>

# Optional — only used when PROVEDOR_IA=local (jarvis/cerebro/voz_local/, the
# alfred-server running in Docker on this machine). All have working defaults;
# only set these to override them. NOTE: this broker is NOT the rede_jarvis one
# (MQTT_HOST above) — different host, different port, no TLS, and a separate
# paho client; see the constraint about that below:
VOZ_LOCAL_MQTT_HOST=<broker hostname, default "localhost">
VOZ_LOCAL_MQTT_PORT=<default 1884 — NOT 1883, see the two-broker note below>
VOZ_LOCAL_MQTT_USERNAME=<optional — the server runs without auth today>
VOZ_LOCAL_MQTT_PASSWORD=<optional>
VOZ_LOCAL_MQTT_TLS=<true/false, default false — a local broker has no certificate>
VOZ_LOCAL_TOPICO_ENTRADA=<stage 1 in, default "jarvis/audio/entrada">
VOZ_LOCAL_TOPICO_TEXTO_SAIDA=<stage 1 out, default "jarvis/texto/saida">
VOZ_LOCAL_TOPICO_TEXTO_ENTRADA=<stage 2 in, default "jarvis/texto/entrada">
VOZ_LOCAL_TOPICO_SAIDA=<stage 2 out, default "jarvis/audio/saida">
VOZ_LOCAL_TOPICO_ERRO=<default "jarvis/audio/erro" — ONE topic for both halves;
  the server prefixes the line with "transcrição: " or "resposta: ">
VOZ_LOCAL_TIMEOUT_TRANSCRICAO_SEGUNDOS=<seconds, default 25 — stage 1, STT only>
VOZ_LOCAL_TIMEOUT_RESPOSTA_SEGUNDOS=<seconds, default 40 — stage 2, LLM + TTS.
  A timeout in either stage reports the failure and goes back to listening;
  it never ends the call>
VOZ_LOCAL_LIMIAR_PROB_FALA=<0 to 1, default 0.5 — the VAD threshold. This is a
  PROBABILITY that the block contains human speech, from the Silero VAD model,
  NOT a volume. Raising it makes it stricter about the sound being a voice, not
  deafer to quiet sounds. Lower it if it doesn't hear you, raise it if something
  that isn't speech opens an utterance>
VOZ_LOCAL_MODELO_VAD=<path to a Silero .onnx to use instead of the one fetched
  automatically. Optional; unset, the model resolves itself on first call and is
  cached in dados/modelos/>
VOZ_LOCAL_LIMIAR_VOZ=<0 to 1, default 0.12 — AMPLITUDE threshold, compared against
  the same calcular_nivel_audio value that animates the sphere. Only used in the
  emergency mode, when the Silero model can't be loaded; with the VAD working,
  changing this does nothing>
VOZ_LOCAL_SILENCIO_SEGUNDOS=<seconds of NON-SPEECH that close an utterance, default
  1.0. Unchanged by the Silero switch: only HOW each block is classified changed,
  never how much non-speech ends the phrase>

# Optional — only needed for the consultar_cotacao_acao / consultar_historico_acao
# tools (consulta_acoes package), a free key from twelvedata.com:
TWELVE_DATA_API_KEY=<your key>

# Optional — whether most package tools are declared to the voice brain or
# discovered on demand by the sub-agent (jarvis/pacotes/agente_ferramentas/).
# Default true, and the saving is the whole point: the per-turn prefix went
# from 18.182 to 9.214 tokens. Set to false to declare everything again, which
# is the escape hatch if the model starts behaving worse without seeing the
# list. Read by jarvis/nucleo/config.py, applied in perfis.preparar_chamada():
FERRAMENTAS_SOB_DEMANDA=<true (default) or false>

# Optional — only used by the buscar_ferramenta / executar_ferramenta tools
# (agente_ferramentas package). GROQ_API_KEY is REUSED, not a new credential:
AGENTE_FERRAMENTAS_CATALOGO_COMPLETO=<true/false, default false — true uses the
  full FunctionDeclaration descriptions in the search catalog: more precise,
  but over 10k tokens, which blows the Groq free tier in a single call>

# Optional — controls whether the in-call keyword auth gate ("Coisa") is enforced.
# Default true (the security behavior never changes on its own) if unset; only
# `false` disables it. See jarvis/nucleo/config.py — EXIGIR_AUTENTICACAO:
EXIGIR_AUTENTICACAO=<true (default) or false>

# Optional — only needed for the preparar_email/confirmar_envio_email / ler_emails tools:
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_REMETENTE=<sender/account address>
EMAIL_SENHA_APP=<app password, not the account password>

# Optional — only needed for the enviar_comando_remoto tool (rede_jarvis package):
MQTT_HOST=<broker hostname, e.g. a HiveMQ Cloud cluster>
MQTT_PORT=8883
MQTT_USERNAME=<broker username, same on every machine>
MQTT_PASSWORD=<broker password, same on every machine>
TOKEN_REDE_JARVIS=<shared secret, same value on every machine>
NOME_MAQUINA=<this machine's name, e.g. "casa" or "loja">
PASTA_TRANSFERENCIAS_PADRAO=<fallback save folder for received files>
GOOGLE_SERVICE_ACCOUNT_JSON=<path to this machine's Drive service-account key file>
PEDIR_PERMISSAO=true

# Optional — only needed for the controlar_dispositivo_casa tool (casa_inteligente package):
TUYA_ACCESS_ID=<Client ID from the Tuya IoT Platform Cloud Project>
TUYA_ACCESS_SECRET=<Client Secret from the same Cloud Project>
TUYA_API_ENDPOINT=<API base URL matching the Cloud Project's actual Data Center — confirm in its Overview tab, don't guess>

# Optional — only needed for the executar_comando_admin tool (admin_terminal package).
# All have working defaults; only set these to override them:
ADMIN_TERMINAL_NOME_TAREFA=<Scheduled Task name, default "JarvisAdminTerminal">
ADMIN_TERMINAL_TIMEOUT_PADRAO=<seconds, default 30>
ADMIN_TERMINAL_TIMEOUT_LONGO=<seconds, default 300 — used when a command is called with execucao_longa=true>
ADMIN_TERMINAL_TIMEOUT_CONFIRMACAO=<seconds, default 40 — how long a non-whitelisted command waits for voice/notification confirmation before failing safe (denied)>

# Optional — only needed for the identificar_planta tool (identificacao_planta package):
PLANTNET_API_KEY=<free API key from my.plantnet.org, Settings > API key>
PLANTNET_PROJETO=<Pl@ntNet flora/project to search, default "all">
PLANTNET_TIMEOUT_SEGUNDOS=<seconds, default 15>

# Optional — only needed for the consultar_segunda_opiniao_visual tool
# (identificacao_visual package). MISTRAL_API_KEY is shared/reused — it may
# already be set from an earlier, unrelated addition to this .env. Which
# provider answers is a POLICY, not a fixed default: leave
# DESCRICAO_VISUAL_PROVEDOR unset and the second opinion automatically uses the
# provider OPPOSITE the active voice brain (Mistral when PROVEDOR_IA=gemini,
# Gemini in openai/local mode), so it is never the same model confirming
# itself; set it to force one provider manually, for both vision packages:
DESCRICAO_VISUAL_PROVEDOR=<unset (recommended — automatic rule), "gemini" or "mistral">
MISTRAL_API_KEY=<API key from console.mistral.ai>
IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS=<seconds, default 20>

# Optional — only needed for the enviar_dm_discord / enviar_mensagem_discord tools
# (discord_jarvis package). Requires "Server Members Intent" AND "Message Content
# Intent" enabled under Privileged Gateway Intents in the Developer Portal
# (discord.com/developers/applications) — confirmed live, the connection fails
# explicitly without them. The bot also needs to be invited to a server the target
# people/channels are actually in.
DISCORD_BOT_TOKEN=<bot token from the Developer Portal, Bot tab>
DISCORD_TIMEOUT_CONEXAO=<seconds, default 15>
DISCORD_TIMEOUT_OPERACAO=<seconds, default 15>
DISCORD_TIMEOUT_LISTAGEM_MEMBROS=<seconds, default 30>

# Optional — only needed for voice-activated call start (ativacao_voz package).
# No account or API key needed at all — recognition runs 100% locally via Vosk;
# the package downloads its own Portuguese model (~31MB) automatically on first use
# (cached after that, no re-download). Until that first download finishes, voice
# activation just isn't ready yet — the manual "INICIAR CHAMADA" button always
# works regardless:
NOME_ATIVACAO=<activation word/phrase, default "iniciar chamada" — must be a real
  word the Vosk Portuguese model's closed vocabulary actually contains (confirmed
  live via Model.vosk_model_find_word() — the model can NEVER recognize a word
  outside its vocabulary, not even in grammar-constrained mode; foreign-origin
  proper nouns like "jarvis" are a common case that's absent and silently
  unrecognizable no matter how clearly spoken — this is why "jarvis" was replaced
  as the default). Accuracy is also lower than a dedicated wake-word engine since
  this is generic speech recognition, not purpose-built keyword spotting>

# Optional — how long a call can sit with zero real activity (the assistant
# speaking or executing a function — never just microphone noise) before it hangs
# up on its own, warning by voice first. Read directly by jarvis/nucleo/config.py (unlike
# every other TIMEOUT_* constant in jarvis/cerebro/gemini/cliente_live.py, which are
# hardcoded, not .env-configurable — this one is env-configurable because the
# feature request explicitly asked for it that way):
TIMEOUT_INATIVIDADE_SEGUNDOS=<seconds, default 300>

# Optional — only needed for the criar_arquivo tool (criar_arquivo package):
PASTAS_PERMITIDAS_CRIACAO=<comma-separated absolute paths, default (if unset) is
  this machine's Desktop, Documents, and Downloads folders — NEVER the whole
  disk. A spoken folder name only ever resolves against this list; a name that
  doesn't match is rejected with the list of allowed folders, never guessed>

# Optional — only needed for the abrir_aplicativo tool (abrir_aplicativo
# package). Does NOT relax the whitelist-only behavior (still only apps the
# Windows aliases, the Start Menu, Get-StartApps or this list already know
# about) — just widens the search to also cover portable programs that never
# show up in the Start Menu:
PASTAS_EXTRAS_APPS=<comma-separated absolute paths, optional — a shallow (folder
  itself + one level of subfolders, never a deep recursive scan) search for
  .exe files, combined with the existing Get-StartApps results>
```

`admin_terminal` also requires a one-time **manual** setup step per machine before its
tool works at all — see its section under Architecture below. This is not part of
`pip install`/`.env` and is deliberately never run automatically.

## Repository layout

Everything under `jarvis/` is source; everything under `dados/` is state this
machine generated. Nothing writes a data file next to its own code.

```
main.py                     entry point (`python main.py`)
config.json                 machine-local preferences (interrupcao, microfone...)
                            + "modelos": every brain and sub-agent model id
.env                        credentials (gitignored)
docs/INTEGRATION.md         the package-rewiring contract
dados/                      memoria.json, *_conhecidos caches, admin_fila/, logs/,
                            audios/avisos_ferramenta/ (aviso falado de ferramenta)
  perfis/<slug>/            perfil.json + sistema.md +
                            manual_ferramentas.md + ferramentas_diretas/
                            (lista_ferramentas_diretas.md + um <tool>.md
                            por ferramenta declarada). So o perfil
                            "completo" tem os dois ultimos; os outros
                            caem nele
testes/                     scripts de verificação rodados à mão
jarvis/
  caminhos.py               RAIZ_PROJETO / CAMINHO_ENV / CAMINHO_CONFIG_JSON /
                            PASTA_DADOS / PASTA_LOGS / garantir_pasta()
  nucleo/                   config.py, preferencias.py, sinalizador.py, prompts/
  cerebro/                  os tres cerebros de voz, um subpacote cada
    gemini/cliente_live.py  GeminiLiveWorker (PROVEDOR_IA=gemini, padrao)
    openai_realtime/        OpenAIRealtimeWorker (PROVEDOR_IA=openai)
    voz_local/              VozLocalWorker (PROVEDOR_IA=local, alfred-server)
                            + vad_silero.py (deteccao de fala, Silero VAD)
  nucleo/perfis/            perfis: armazenamento, catálogo, sensíveis, geração
  ui/                       janela_principal / janela_chat /
                            janela_envio_arquivo / janela_camera /
                            visualizador_alfred (a esfera) +
                            painel_chat_sobreposto (chat sobre ela)
  servicos/agentes/         a camada unica de chamada de LLM (LangChain):
                            agente.py (PedidoAgente/RespostaAgente),
                            modelos.py, mensagens.py, ferramentas.py,
                            erros.py
  servicos/visao/           captura_tela, captura_camera, monitor_continuo
  servicos/email/           remetente (SMTP), leitor (IMAP)
  servicos/memoria/         gerenciador
  pacotes/<pacote>/         one isolated package per integration
```

**Never recompute the project root by counting `.parent` hops** — import from
`jarvis/caminhos.py` instead. The single sanctioned exception is
`jarvis/pacotes/admin_terminal/runner_elevado.py`, which the Scheduled Task runs
as a loose script with the project root absent from `sys.path`, so it cannot
import `jarvis` at all; it computes `parents[3]` and says so in a comment, and
its `_PASTA_FILA` must stay pointed at the same folder as
`admin_terminal/config.py`'s `PASTA_FILA`.

This layout replaced a flat root of 20+ sibling folders (`core/`, `config/`,
`gemini/`, `ui/`, `vision/`, `mailer/`, `memory/`, `interfaces_extras/` plus all
14 packages). Renames from that layout: `main_basic.py` → `main.py`,
`gemini/live_client_basic.py` → `jarvis/cerebro/gemini/cliente_live.py`,
`ui/main_window_basic.py` → `jarvis/ui/janela_principal.py`,
`ui/chat_window.py` → `janela_chat.py`, `ui/envio_arquivo_window.py` →
`janela_envio_arquivo.py`, `ui/camera_window.py` → `janela_camera.py`,
`config/carregador.py` → `jarvis/nucleo/preferencias.py`,
`interfaces_extras/sinalizador.py` → `jarvis/nucleo/sinalizador.py`,
`vision/screen_capture.py` → `servicos/visao/captura_tela.py`,
`vision/camera_capture.py` → `servicos/visao/captura_camera.py`,
`mailer/email_sender.py` → `servicos/email/remetente.py`,
`mailer/email_reader.py` → `servicos/email/leitor.py`,
`memory/memory_manager.py` → `servicos/memoria/gerenciador.py`,
`memory/memory.json` → `dados/memoria.json`. The `_basic` suffix is gone but its
meaning is not: `main.py`, `jarvis/cerebro/gemini/cliente_live.py` and
`jarvis/ui/janela_principal.py` are still the three course-project files to edit
as little as possible (see the constraint about them further down).

## Prompts (`jarvis/nucleo/prompts/`)

Every hardcoded instruction text sent to any model (Gemini, Groq, Cerebras,
OpenAI, Mistral) anywhere in the project lives here — centralized in one
pass, with every extraction verified byte-for-byte (sha256 of the old
constant's value compared against the new one) before moving it.

`prompts/` is a **package**, not a `prompts.py` module, even though it's
imported and used exactly like one (`from jarvis.nucleo import prompts`,
`prompts.ANUNCIO_ESPONTANEO`) — Python doesn't allow a module and a
same-named package side by side in one directory, and the prompt `.md`
files need to live in files inside it.

**Organized by cérebro, one subfolder each — the same split as
`jarvis/cerebro/`**, so a prompt can be edited without touching a cérebro it
doesn't belong to:
- `prompts/gemini/` — exclusive to Gemini Live (e.g.
  `cruzamento_segunda_opiniao.md`).
- `prompts/openai/` — exclusive to OpenAI Realtime (empty today — nothing
  is OpenAI-Realtime-only, it reuses everything from `geral/`).
- `prompts/local/` — exclusive to voz_local/alfred-server (e.g. the visual
  description prompts, since that's the one cérebro with no native image
  input).
- `prompts/geral/` — reused by more than one cérebro: the auth block
  (`geral/autenticacao.md`, shared by Gemini Live and OpenAI Realtime), and
  every tool-result prompt that works with whichever cérebro is active
  (delegação, segunda opinião visual, consolidação de memória, criação de
  perfil, etc.).

Every prompt is a `.md` file holding the exact final text (with the same
`{campo}` markers the old Python constant had, for the same `.format()`
call sites), loaded in `prompts/__init__.py` via
`_carregar_arquivo("<subpasta>/<arquivo>.md")` and exposed as a Python
constant — a straight read plus stripping the trailing newline the editor
left, no other transformation, so the `.md` content must be byte-for-byte
what's sent to the model.

**One deliberate exception, never extracted to a `.md`**: a prompt line
with a variable spliced into the *middle* of the sentence — e.g.
`f"Você é {obter_nome_jarvis()}, o assistente pessoal..."` in
`jarvis/cerebro/voz_local/contexto.py` — stays as an f-string in the code
file it's in. Pulling just that fragment into `prompts/` wouldn't make it
any easier to edit without touching code, and would split the sentence in
two. Only the fixed text *around* such a line (when there is any, like the
memory-facts intro that follows it) becomes a `.md` file.

`instrucao_sistema`'s full body (~22k chars) doesn't live in `prompts/` at
all anymore — it moved to the active profile, `dados/perfis/<slug>/sistema.md`
(see docs/perfis.md); `prompts.instrucao_sistema_corpo()` reads it from
there at every call start. `bloco_autenticacao` is the one genuinely long
prompt still in this folder (`geral/autenticacao.md`), because it belongs
to no profile — it's the security gate that applies to all of them,
regardless of which cérebro or profile is active.

**How `geral/autenticacao.md` (and the profile's `sistema.md`) are loaded,
and why it's safer than the original Python pattern**: `_carregar_prosa()`
reads the file, drops blank lines and lines starting with `##` (section
headers — pure human navigation, exactly like the old `# IDENTIDADE`/`#
PERSONALIDADE` Python comments, never part of the text sent to the model),
then joins every remaining line by appending a single space to **each**
line before concatenating — never relying on a line's own trailing
whitespace. This is deliberately more robust than the original
adjacent-string-literal-concatenation pattern: a missing trailing space in
the `.md` source can no longer jam two words together, because the loader
supplies the separating space itself regardless of what's in the file.
`instrucao_sistema_corpo()` returns text already ending in `"\n\n"` (the
separator before the memory context that gets concatenated after it in
`cliente_live.py`/`cliente_realtime.py`) — that's added inside the
function, not baked into the `.md` file, so the file's own whitespace can
be freely normalized without disturbing that meaningful separator. Every
other `.md` file in `prompts/` (everything under `gemini/`, `openai/`,
`local/` and `geral/` besides `autenticacao.md`) is loaded with
`_carregar_arquivo()` instead — a plain read with no line-joining and no
`"ALFRED"` substitution, because those prompts are short enough that their
`.md` source already IS the final text, internal blank lines included
where the original had a real `\n\n` paragraph break.

**The `enviar_tela_para_gemini`/`enviar_camera_para_gemini` duplication was
unified** into one `prompts.ANALISE_IMAGEM_PONTUAL` template taking
`{origem}` (`"tela"` or `"câmera"`) — the two were byte-identical except for
that one word (both use the article "da", so no other grammar adjustment
was needed).

**Package isolation vs. centralization — a real tension, flagged and then
resolved per explicit instruction**: several of the packages this task
touched (`delegacao_ia`, `identificacao_visual`, `memoria_obsidian`,
`cerebro_reserva`, since removed) are documented elsewhere in this file as deliberately
self-contained/"decoupled on purpose... to be copied to another project
as-is." Importing `jarvis.nucleo.prompts` into them cuts against that
principle. The user asked for this centralization explicitly, naming these
exact packages, so it was done as asked rather than re-litigated — but if
one of these packages is ever actually extracted to another project, its
prompt constants would need to come along from `jarvis/nucleo/prompts/`
too, or be re-inlined at that point.

**What was deliberately left out of this centralization**: `FunctionDeclaration`
descriptions (tool schemas) — these are tightly coupled to their parameter
definitions and scattered by design across every package's own
`obter_function_declarations()`; moving them would be a much larger,
higher-risk refactor unrelated to what was asked. Also left alone: the
dynamic status strings passed through `callback_falar` in
`rede_jarvis/permissoes.py` and `admin_terminal/confirmacao.py` (e.g. "fulano
pediu permissão remota...") — these are event descriptions, not instructional
prompts; they get wrapped by `prompts.ANUNCIO_ESPONTANEO` downstream, but
aren't prompts themselves. `identificacao_planta` (Pl@ntNet) sends no text
prompt at all — image-only API, confirmed by reading the client, not
assumed.

## Architecture — visão geral

Three-layer flow, entry point `main.py`:

1. **UI layer** — `jarvis/ui/janela_principal.py` (`MainWindow`). Ver `docs/ui.md`.
2. **Gemini Live worker** — `jarvis/cerebro/gemini/cliente_live.py` (`GeminiLiveWorker`), o núcleo do app: conexão assíncrona com o Gemini Live, dispatch de tool calls (nativas e de pacotes), watchdogs de trava/reconexão. Ver `docs/gemini-live-worker.md` antes de editar este arquivo.
3. **Módulos de apoio e pacotes** — cada integração vive isolada em `jarvis/pacotes/<pacote>/` (contrato `obter_function_declarations()`/`despachar()`, ver `docs/INTEGRATION.md`), ou em `jarvis/servicos/`/`jarvis/cerebro/` para infraestrutura compartilhada entre pacotes.

**Antes de editar qualquer arquivo dentro de uma dessas áreas, leia o `docs/*.md` correspondente primeiro** — cada um documenta as decisões de design e as restrições ("nunca faça X porque Y quebrou Z") daquela área específica, extraídas do histórico real do projeto:

- `docs/abrir_aplicativo.md` — jarvis/pacotes/abrir_aplicativo/ (substituiu abrir_app_local)
- `docs/admin_terminal.md` — jarvis/pacotes/admin_terminal/
- `docs/agente_ferramentas.md` — jarvis/pacotes/agente_ferramentas/ — sub-agente que descobre qual ferramenta usar
- `docs/agentes.md` — jarvis/servicos/agentes/ — a camada unica de chamada de LLM (LangChain)
- `docs/agenda.md` — jarvis/pacotes/agenda/
- `docs/arquivos_area_trabalho.md` — jarvis/pacotes/arquivos_area_trabalho/
- `docs/ativacao_voz.md` — jarvis/pacotes/ativacao_voz/
- `docs/camera_preview.md` — jarvis/pacotes/camera_preview/
- `docs/casa_inteligente.md` — jarvis/pacotes/casa_inteligente/
- `docs/chat_jarvis.md` — jarvis/pacotes/chat_jarvis/
- `docs/clique_visual.md` — jarvis/pacotes/clique_visual/
- `docs/configuracoes.md` — jarvis/pacotes/configuracoes/
- `docs/consulta_acoes.md` — jarvis/pacotes/consulta_acoes/
- `docs/controle_mouse.md` — jarvis/pacotes/controle_mouse/
- `docs/criar_arquivo.md` — jarvis/pacotes/criar_arquivo/
- `docs/delegacao_ia.md` — jarvis/pacotes/delegacao_ia/
- `docs/discord_jarvis.md` — jarvis/pacotes/discord_jarvis/
- `docs/escrita_texto.md` — jarvis/pacotes/escrita_texto/
- `docs/explorador_windows.md` — jarvis/pacotes/explorador_windows/
- `docs/fechar_app.md` — jarvis/pacotes/fechar_app/
- `docs/gemini-live-worker.md` — Gemini Live worker (jarvis/cerebro/gemini/cliente_live.py) — núcleo do app
- `docs/identificacao_planta.md` — jarvis/pacotes/identificacao_planta/
- `docs/identificacao_visual.md` — jarvis/pacotes/identificacao_visual/
- `docs/memoria_obsidian.md` — memoria_obsidian/ — sistema de memória em vault Obsidian
- `docs/navegador_web.md` — jarvis/pacotes/navegador_web/ (substituiu navegador_jarvis)
- `docs/nucleo-core.md` — jarvis/nucleo/ — config, sinalizador, registro de pacotes
- `docs/openai_realtime.md` — jarvis/cerebro/openai_realtime/ — segundo cérebro de voz
- `docs/perfis.md` — jarvis/nucleo/perfis/ — perfis de ferramentas
- `docs/pesquisa_web.md` — jarvis/pacotes/pesquisa_web/
- `docs/rede_jarvis.md` — jarvis/pacotes/rede_jarvis/
- `docs/servicos-compartilhados.md` — jarvis/servicos/ — visão, email, memória (legado)
- `docs/ui.md` — UI (janela principal, painéis, esfera animada, chat sobreposto)
- `docs/voz_local.md` — jarvis/cerebro/voz_local/ — terceiro cérebro de voz (servidor local)

## Key constraints to preserve when editing (globais — valem para o projeto inteiro)

- The voice keyword authentication gate in the system prompt is a deliberate security/access-control feature of the assistant persona — don't strip it out during refactors. `EXIGIR_AUTENTICACAO=false` in `.env` is the one sanctioned, explicit, default-safe way to disable it (see `jarvis/nucleo/config.py` / the `bloco_autenticacao` splice in `executar()`) — don't add a second way to bypass it, and don't change the default away from `true`. **Don't compress its wording either**: a rewrite about a third shorter that kept every rule — including the explicit closing line "Não execute funções e não converse sobre outros assuntos antes da autenticação" — still let an unauthenticated "abre o bloco de notas" reach `buscar_ferramenta` in 1 of 12 live runs, while the original text had no such failure in over 50 runs. Keep `geral/autenticacao.md` word for word; see docs/perfis.md.
- Any new `.env`-reading module (inside `jarvis/pacotes/` or not) should get a `config_schema()` and a line in `jarvis/pacotes/configuracoes/pacotes.py`'s `PACOTES_COM_CONFIG` — this list is not restricted to `jarvis/pacotes/` modules (see `jarvis/nucleo/config.py` and `jarvis/servicos/email/`'s two modules, added specifically to close that gap), so there's no excuse to skip it for a module living elsewhere.
- Vision and email functions are intentionally *not* auto-triggered by the model — restricted to explicit user requests, and for `preparar_email` specifically the recipient/subject/body must have been stated by the user rather than invented. Preserve these restrictions. Since the direct-tools list, they live in **two places that must both keep them**: two lines in the "SEGURANÇA DAS AÇÕES LOCAIS" section of `dados/perfis/completo/sistema.md`, and the *lock* (the part after the dash) of each vision/email line in `dados/perfis/completo/ferramentas_diretas/lista_ferramentas_diretas.md` — that line becomes the tool's schema description, so it is what the model sees at the moment it decides. The detailed rules are in each tool's `<tool>.md`, read only on use.
- **New tools/integrations always live in their own isolated package under `jarvis/pacotes/`** (`jarvis/pacotes/rede_jarvis/`, `jarvis/pacotes/casa_inteligente/`, `jarvis/pacotes/delegacao_ia/` are the existing examples), never as business logic dropped into one of the three course-project files. Every such package exposes exactly `obter_function_declarations()` and `despachar(nome_funcao, argumentos)` — the standard contract in **docs/INTEGRATION.md** — so it can be wired into any client file with the same three touch points, not bespoke code per package.
- The three course-project files (`main.py`, `jarvis/cerebro/gemini/cliente_live.py`, `jarvis/ui/janela_principal.py` — formerly the `_basic`-suffixed ones) are temporary and will be fully replaced once the finished course project lands — **edit them as little as possible**. For a package, that now means only: (1) one line in `jarvis/nucleo/registro_pacotes.py` and (2) the tool's usage rules in the default profile — a section citing the tool by name in `dados/perfis/completo/manual_ferramentas.md` for a hidden tool (the normal case), or a line in `ferramentas_diretas/lista_ferramentas_diretas.md` plus `ferramentas_diretas/<tool>.md` for a declared one. **Not `sistema.md` anymore**: it is paid on every turn and holds only identity, safety and the tool-use flow. **Neither of these is one of the three files.** `PACOTES_REGISTRADOS` used to live inside `cliente_live.py`; it moved out precisely so that registering a package stopped touching them at all. Anything beyond that (new business logic, new state, new helper methods) belongs inside the package itself, not in one of those three files. Packages that need session-glue callbacks (like `rede_jarvis`) are the only sanctioned exception, and even those are documented as copy-paste snippets in docs/INTEGRATION.md, not open-ended edits.
- **docs/INTEGRATION.md must be updated every time a package is added or its integration surface changes** — new/changed `obter_function_declarations()`/`despachar()` behavior, a new or changed session-glue callback, etc. It is the single source of truth for re-wiring packages into a future (post-course) client file; letting it drift out of sync defeats its purpose.
- **Qt threading discipline**: `GeminiLiveWorker` (a `QThread`) never touches UI widgets directly. All communication back to `MainWindow` goes through its `Signal`s (`status_recebido`, `erro_recebido`, `chamada_encerrada`, `solicitou_encerramento`, `nivel_audio`), connected once in `jarvis/ui/janela_principal.py`; the worker only ever calls `self.<sinal>.emit(...)`. Preserve this direction — don't add a reference from the worker (or a package it calls) back into `MainWindow`/widgets, and don't call Qt GUI classes (e.g. `QFileDialog`) from a background thread without the same signal/queued-connection bridge pattern `jarvis/pacotes/rede_jarvis/transferencia_arquivos.py` already uses (`_PonteSalvarArquivo`, instantiated on the GUI thread via `preparar_ponte_gui()`).
- **"Enabled" and "declared" are two different things now — don't collapse them.** A voice brain pays every declared tool's schema on every turn (measured: the prefix was 18.182 tokens, now 9.214), so most package tools are NOT declared: the brain finds them with `buscar_ferramenta` and runs them with `executar_ferramenta` (`jarvis/pacotes/agente_ferramentas/`). The profile still decides what is *enabled* — nothing changed there. The subtraction happens in exactly one place, `perfis.preparar_chamada()` → `_sem_as_ocultas()`, which is why none of this touched `cliente_live.py` or `cliente_realtime.py`; keep it that way. The hidden set is **derived** by `registro_pacotes.ferramentas_ocultas()`, never hand-written. **Never move a tool from `TOOLS_QUE_PRECISAM_DE_IMAGEM`, `TOOLS_SILENCIOSAS` or `TOOLS_QUE_CAPTURAM_SOZINHAS` into the hidden set**: both workers recognize those by the *name of the tool call*, and through `executar_ferramenta` that name is `"executar_ferramenta"` — image capture, the visual mutex and turn silencing would all vanish silently, which is the exact bug `TOOLS_QUE_PRECISAM_DE_IMAGEM` already documents. `FERRAMENTAS_SOB_DEMANDA=false` restores the old all-declared behavior, long descriptions included. **Declared tools themselves are cheap now too**: `perfis.filtrar_declaracoes` swaps each one's long description for its one-line entry in the profile's `ferramentas_diretas/lista_ferramentas_diretas.md`, returning **copies** (never mutate — package declarations are module-level objects the sub-agent's catalog also reads), and the brain reads the full rules with `ler_instrucao_ferramenta` once per call. The flow order is deliberate and user-chosen: the brain checks its own list first (free, it's in the prefix) and only then asks the sub-agent, which sees **only hidden tools**. Measured per-turn prefix: 18.182 tokens originally → 3.766 (Gemini Live) / 2.091 (OpenAI Realtime). See docs/agente_ferramentas.md.
- **Every model id lives in `config.json` → `"modelos"`, never in `.env` and never hardcoded.** Two groups: `cerebro` (Gemini Live model, its fallback and voice; OpenAI Realtime model and voice) and `subagentes` (agente_ferramentas, roteamento_hierarquico, delegacao_ia, descricao_visual, identificacao_visual, consolidacao_memoria, localizador_clique). Code reads them only through `jarvis.nucleo.modelos.modelo("subagentes.delegacao_ia.groq")`, whose `PADROES` holds the defaults used when a key is missing (with a printed warning). A new sub-agent model means a key in `PADROES` **and** in `config.json`. The `.env` keeps credentials and behavior switches (`PROVEDOR_IA`, `DESCRICAO_VISUAL_PROVEDOR`); the old `*_MODELO_*`/`GEMINI_VISION_MODEL` variables are no longer read. `preferencias.salvar_preferencia` rewrites the whole file, so it must keep preserving every top-level section besides `"config"` — writing only `{"config": [...]}` again would silently erase the models.
- **Every LLM call goes through `jarvis/servicos/agentes/` (LangChain) — never a client opened in place.** One `PedidoAgente` in, one `RespostaAgente` out, `executar()` never raises; see docs/agentes.md and the "Como um pacote consulta uma LLM" section of docs/INTEGRATION.md. This covers text and vision, all five providers (Gemini, OpenAI, Groq, Cerebras, Mistral). The mechanical check is `grep -rn "genai.Client\|requests.post" jarvis/`: the only legitimate hits are `jarvis/cerebro/gemini/cliente_live.py` (the Live session), `jarvis/cerebro/gemini/gerador_avisos.py` (a Live session that records the tool-notice clips in the brain's own voice — the Gemini TTS models allow only 10 requests/day on the free tier, and LangChain does not model Live sessions) and `jarvis/pacotes/identificacao_planta/plantnet_client.py` (Pl@ntNet is not an LLM). The three VOICE brains (`jarvis/cerebro/`) are deliberately outside this layer — they are bidirectional realtime audio sessions, which LangChain does not model; don't try to port them onto it. Two dependency constraints that are load-bearing, both explained in requirements.txt: `langchain-openai` must stay `>=1.6.2` (the 0.3.x line pins `openai<3` and would downgrade the SDK the OpenAI Realtime brain uses), and `langchain-cerebras` is deliberately NOT a dependency (it requires Python <3.13; Cerebras is reached via `ChatOpenAI` + `base_url`, its API being OpenAI-compatible).
- **OpenAI has exactly TWO sanctioned entry points, and no third.** (1) `delegacao_ia.delegar_tarefa(tipo_tarefa="segunda_opiniao", ...)` — the single, rarely-used, no-fallback route in `jarvis/pacotes/delegacao_ia/roteador.py`, deliberate because OpenAI is the most expensive provider in use. (That route now reaches OpenAI through `jarvis/servicos/agentes/`, which is the shared transport for every provider, not a door of its own — the policy about who may call OpenAI and how often still lives entirely in `delegacao_ia/roteador.py`.) (2) `jarvis/cerebro/openai_realtime/cliente_realtime.py`, the alternative voice brain, reachable ONLY when the user sets `PROVEDOR_IA=openai` in `.env` — added at the user's explicit request after being told about this constraint, not as a drive-by. Don't add a third code path that calls OpenAI directly from anywhere else, and don't make the Realtime worker reachable by anything other than that one `.env` variable (`usar_provedor_openai()` in `jarvis/nucleo/config.py`, read by `_classe_do_worker()` in `jarvis/ui/janela_principal.py` — that is the whole surface).
- **Portuguese-only convention is not optional**: every identifier, comment, docstring, UI string, and `instrucao_sistema`/tool-result string added to this codebase must be in Brazilian Portuguese, matching the existing files — this includes new packages, not just edits to existing ones.
- `jarvis/ui/janela_principal.py` never gains new UI (buttons, menus, dialogs) for a package's feature — any package that needs to show its own window emits a `Signal` on `jarvis.nucleo.sinalizador` instead (see `jarvis/pacotes/configuracoes/`'s section above and docs/INTEGRATION.md), connected from `main.py`. This keeps the main window ignorant of every package built on top of it, matching the same "don't touch the course-project files beyond the standard touch points" principle applied to the UI layer specifically.
- Never print, log, or otherwise surface a sensitive `.env` value (API key, token, password, secret) in plain text outside the masked field it belongs to — this applies to `jarvis/pacotes/configuracoes/window.py` specifically (a sensitive field's value must never appear in a `print()`, an exception message, or anywhere but that one `QLineEdit`), on top of the project-wide rule of never hardcoding or echoing credentials.
- **Every send to a voice session must go through that worker's `_enviar_para_sessao` wrapper** (`asyncio.wait_for` + `TIMEOUT_ENVIO_SESSAO_SEGUNDOS`), in both `jarvis/cerebro/gemini/cliente_live.py` and `jarvis/cerebro/openai_realtime/cliente_realtime.py` — never a bare `await` on `send_client_content`/`send_realtime_input`/`send_tool_response`/`conversation.item.create`/`response.create`/`input_audio_buffer.append`. In the OpenAI worker this is doubly load-bearing because every send is made while holding `self.lock_envio`: a hung send never returns the lock, so every later tool call blocks forever waiting to answer its own `function_call_output` — and the protocol forbids the model from speaking again until that answer arrives, so the call ends up alive and mute while the three core tasks stay healthy and the supervision loop sees nothing wrong. The mechanical check is `grep -nE "await (self\.)?conexao\.(conversation|response|input_audio_buffer)"` over that file: any hit is a bare send. Whoever detects the stall must never try to announce it by voice — that announcement is itself a send down the same stalled path.
- **Speech interruption now exists in the OpenAI Realtime worker too**, driven by the same `config.json` → `interrupcao` preference. Its three microphone barriers must all call `_microfone_bloqueado()` — never re-inline the condition in one of them — and its mic-queue clearing must stay behind `if not self.interrupcao_habilitada`. The interruption itself (`_interromper_fala`) sends `conversation.item.truncate` through `_enviar_para_sessao` inside a `try`, with `audio_end_ms` from bytes actually played, rounded down. See docs/openai_realtime.md and docs/INTEGRATION.md.
- **A tool result must never get lost, and a slow tool must never look like a frozen app — both workers.** Measured live: when the user speaks while a Gemini tool is running, the server sends `tool_call_cancellation` and silently discards the `tool_response` for that id; the model, with no result, then said "o arquivo foi criado com sucesso" about a file that did not exist (the user's real report). `GeminiLiveWorker` now keeps the cancelled ids (`_registrar_cancelamento`) and `_enviar_respostas` delivers those results as a normal user turn (`prompts.RESULTADO_CHAMADA_INTERROMPIDA`, image included), also covering a cancellation that crosses an already-sent response (`respostas_recentes`). Never go back to a bare `send_tool_response` in `_enviar_resposta_funcao`/`_responder_falha_para_lote` — both must go through `_enviar_respostas`. The OpenAI worker needs no equivalent: its microphone stays closed while `processando_ferramenta` is true and the output always goes through `function_call_output`. Also in both workers: a tool still running after `aviso_ferramenta.LIMITE_SEGUNDOS` (1.5s) plays a pre-recorded "Só um minuto, estou executando a ferramenta X" through the normal output queue (the model cannot speak during a synchronous call — `gemini-3.1-flash-live-preview` has no `NON_BLOCKING`); every tool execution prints `[FERRAMENTA]` lines to the console and emits "Executando a ferramenta X..."; and the status goes back to "<nome> está ouvindo." when the turn after a tool ends. The clips live in `dados/audios/avisos_ferramenta/<voz>/<ferramenta>.wav`, one per tool, generated with the brain's own Live model and voice by `python -m jarvis.cerebro.gemini.gerador_avisos` (each clip is checked against its transcription). Run it again after adding a tool or changing `cerebro.gemini.voz`; a tool without a clip falls back to `_generico.wav`. See docs/gemini-live-worker.md and docs/servicos-compartilhados.md.
- **Every function-call `asyncio.Task` must be kept in `self.tarefas_funcao_ativas` with an `_ao_finalizar_tarefa_funcao` done-callback**, in both workers. This is not tidiness: asyncio holds only a *weak* reference to a running task, so a fire-and-forget `create_task` can be garbage-collected mid-flight — and a `function_call_output` that never gets sent leaves the model waiting on that `call_id` forever. The `LIMITE_TAREFAS_FUNCAO_SIMULTANEAS` check must stay a synchronous list-length comparison made *before* creating the task (never a wait, which would reintroduce the blocking it exists to prevent), and going over the limit must **refuse by answering** the `call_id`, never by silently dropping or queueing it.
- **The reference JARVIS project at `C:\Users\massa\JARVIS` uses `"defaultMode": "bypassPermissions"` + `skipDangerousModePermissionPrompt` in its `.claude/settings.json`. This project deliberately does NOT adopt that**, and the absence of a `.claude/settings.json` here is a decision, not an oversight. That project's agent writes documents and web pages; this one runs elevated admin commands through a Scheduled Task, drives the real mouse and keyboard, closes arbitrary processes, sends email and Discord messages, and controls smart-home devices. Blanket permission bypass would remove the last confirmation step in front of every one of those. If a permissions file is ever added here, it must be a narrow allowlist of read-only commands, never a global bypass.
