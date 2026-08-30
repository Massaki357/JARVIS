# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ALFRED is a Windows desktop voice assistant built with PySide6 and the Gemini Live API (`google-genai`). It streams microphone audio to Gemini in real time, plays back the spoken response, and can call a small set of tools (screen capture, continuous screen viewing, webcam capture, persistent memory, sending/reading email, remote commands to other ALFRED instances over MQTT, call termination) that the model triggers by voice. All conversation happens in Brazilian Portuguese, and all identifiers, comments, and UI strings in the codebase are in Portuguese — follow that convention when editing.

This is a learning/course project (`[CURSO]` comments throughout explain Python/Qt/asyncio concepts for the author). Comments are intentionally verbose for teaching purposes; match the existing density if adding to files that already have it, but don't add new `[CURSO]`-style comments yourself.

## Setup and running

No test suite, linter, or build system is configured in this repo.

```powershell
# Activate the venv (already present in ./venv)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the app
python main_basic.py
```

Requires a `.env` file (gitignored) in the project root with:
```
GEMINI_API_KEY=<your key>

# Optional — only needed for the enviar_email / ler_emails tools:
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
```

## Architecture

Three-layer flow, entry point `main_basic.py`:

1. **UI layer** — `ui/main_window_basic.py` (`MainWindow`, `QMainWindow`). Builds the PySide6 window (title, status label, call/analyze buttons, activity log) with an inline QSS stylesheet. Owns a single `GeminiLiveWorker` instance (`self.live_worker`), created fresh on each call and discarded when the call ends. All Gemini-thread signals (`status_recebido`, `erro_recebido`, `chamada_encerrada`, `solicitou_encerramento`, `nivel_audio`) are wired here.

2. **Gemini Live worker** — `gemini/live_client_basic.py` (`GeminiLiveWorker`, a `QThread`). This is the core of the app:
   - Runs its own `asyncio` event loop (`run()` → `asyncio.run(self.executar())`) so the Qt UI thread never blocks.
   - Opens a `client.aio.live.connect(...)` session against `GEMINI_LIVE_MODEL` and runs three concurrent asyncio tasks: `enviar_microfone` (mic → Gemini via `sounddevice.RawInputStream`), `receber_audio` (Gemini → playback queue + tool-call dispatch), `reproduzir_audio` (queue → speakers via `sounddevice.RawOutputStream`).
   - Echo prevention: while `self.alfred_falando` is `True` (assistant is speaking), microphone input is dropped, both at the sounddevice callback level and again when pulling from the queue, plus a queue flush (`limpar_fila_microfone`) whenever new assistant audio starts.
   - `instrucao_sistema` (system prompt) defines ALFRED's identity/personality and, critically, a voice-based authentication gate: the app only responds to commands after the user speaks a secret keyword ("Coisa" — also documented in README.MD). Never remove or weaken this auth logic without being asked.
   - Tool calls from Gemini (`resposta.tool_call`) are dispatched in `processar_chamada_de_funcao` by name: `analisar_tela` / `analisar_camera` (single-frame vision), `iniciar_visualizacao_continua` / `parar_visualizacao_continua` (continuous screen streaming), `enviar_email` (SMTP) / `ler_emails` (IMAP, `pasta` param constrained to the `INBOX`/`SPAM` enum), `enviar_comando_remoto` / `responder_permissao_remota` / `listar_maquinas_remotas` (remote machines over MQTT — see the `rede_jarvis` bullet below), `salvar_memoria` / `listar_memorias` / `esquecer_memoria` (memory), `encerrar_chamada` (ends the call after a short delay so the goodbye line finishes playing, via `solicitou_encerramento` signal back to the UI). Adding a new voice tool means: add a `types.FunctionDeclaration` to the `tools` list, add a branch in `processar_chamada_de_funcao`, and update `instrucao_sistema` with usage rules.
   - Repeated/near-simultaneous single-frame vision-tool calls are throttled via `executando_funcao_visual` (mutex) and `COOLDOWN_FUNCAO_VISUAL` (per-function debounce). This mutex is separate from continuous viewing, which has its own active/inactive state (`self.monitor_tela_continuo`).
   - Continuous screen viewing streams frames to Gemini via `session.send_realtime_input(video=...)` (not `send_client_content`, unlike the single-frame tools) while the mic keeps recording, so it doesn't interrupt the conversation. The `GeminiLiveWorker` owns at most one active `MonitorTelaContinuo` (`vision/monitor_continuo.py`) at a time in `self.monitor_tela_continuo`; it's torn down both by `parar_visualizacao_continua` and, defensively, in `executar()`'s cleanup block when the call itself ends, so it never keeps streaming frames after the session closes.
   - Blocking calls made from inside the async worker (`capturar_tela_bytes`, `enviar_email`) are always wrapped in `asyncio.to_thread(...)` — never awaited directly — since they're synchronous I/O and would otherwise stall the event loop (mic/playback tasks included).

3. **Supporting modules**:
   - `core/config.py` — loads `.env` via `python-dotenv`, exposes `GEMINI_API_KEY`, `GEMINI_LIVE_MODEL`, `GEMINI_VOICE`. Available model/voice options are listed in comments here — swap the active value rather than adding new config plumbing.
   - `vision/screen_capture.py` / `vision/camera_capture.py` — each exposes one function (`capturar_tela_bytes` / `capturar_camera_bytes`) that captures a single frame (via `mss` / `cv2`) and returns in-memory JPEG bytes (via `Pillow`). No files are ever written to disk. These bytes get sent to Gemini as `inline_data` parts alongside a per-call text instruction that tells the model to only use the freshly sent image.
   - `vision/monitor_continuo.py` — `MonitorTelaContinuo`, a standalone asyncio loop (no Gemini/PySide dependency, reusable in other projects) that repeatedly calls `capturar_tela_bytes()` at a configurable interval and hands each frame to an injected async callback, until `parar()` is called or a configurable `timeout_segundos` (default 90s) elapses — in which case it self-stops and invokes an optional `callback_encerrado` so the caller can react (e.g. tell the user it timed out).
   - `mailer/email_sender.py` — `enviar_email(destinatario, assunto, corpo)`, a standalone SMTP sender (stdlib `smtplib`/`email` + its own `load_dotenv()` call — deliberately decoupled from `core/config.py` so the file can be dropped into another project as-is). Reads `EMAIL_SMTP_HOST`/`EMAIL_SMTP_PORT`/`EMAIL_REMETENTE`/`EMAIL_SENHA_APP` from `.env`. Credentials belong in `.env` (gitignored), not `memory.json` — that file is for non-secret user memories only. Returns a human-readable Portuguese string in all cases (success, missing config, invalid input, SMTP/connection failure) rather than raising, matching the convention used by `memory_manager.py`, since the return value is spoken back to the user as the tool result.
   - `mailer/email_reader.py` — `ler_emails(quantidade=5, apenas_nao_lidos=False, pasta="INBOX")`, same standalone/`load_dotenv()` convention as `email_sender.py`, using stdlib `imaplib`/`email`. Reuses `EMAIL_REMETENTE`/`EMAIL_SENHA_APP` from `.env` (same Gmail app password authenticates both SMTP and IMAP) plus `EMAIL_IMAP_HOST`/`EMAIL_IMAP_PORT`. Opens the mailbox `readonly=True` and fetches with `BODY.PEEK[...]` so listing never marks messages as read. For the `SPAM` folder it doesn't hardcode a folder name (`"[Gmail]/Spam"` varies by account language) — it resolves it dynamically via IMAP `LIST`, looking for the folder with the special-use `\Junk` flag, falling back to the literal name only if that lookup fails.
   - `memory/memory_manager.py` — persistent memory store backed by `memory/memory.json` (created on demand), guarded by a `threading.Lock` for read/write safety and atomic writes (write to `.tmp`, then `Path.replace`). Public API: `salvar_memoria`, `listar_memorias`, `esquecer_memoria`, `contexto_memorias` (injected into the system prompt at session start). Enforces `MAXIMO_MEMORIAS` (50 entries) and `MAXIMO_CARACTERES` (200 chars/entry), de-duplicates via accent/case-insensitive normalization (`_normalizar_texto`), and refuses bulk-delete phrases like "esquecer tudo" as a safety guard. `esquecer_memoria` resolves a reference by exact ID, then exact text match, then unique partial match (asks for disambiguation if multiple candidates match).
   - `rede_jarvis/` — a self-contained package for remote command/control between machines running ALFRED, using MQTT as the transport (no VPN/relay server needed — any cloud MQTT broker works, e.g. HiveMQ Cloud). Deliberately isolated from the rest of the app: `gemini/live_client_basic.py` only imports the package, adds the `enviar_comando_remoto`/`responder_permissao_remota`/`listar_maquinas_remotas` `FunctionDeclaration`s, dispatches to `rede_jarvis.enviar_comando_remoto`/`rede_jarvis.responder_permissao_por_voz`/`rede_jarvis.listar_maquinas_online`, and has two small session-glue methods (`_falar_rede_jarvis`, `_receber_frame_remoto`) that adapt the package's abstract callbacks to this specific Gemini session (`send_client_content`/`send_realtime_input`) — no other business logic lives outside the package. See `rede_jarvis/__init__.py`'s docstrings for the full module breakdown (`mqtt_client`, `mqtt_listener`, `comandos`, `visualizacao_remota`, `transferencia_arquivos`, `permissoes`, `notificacoes`, `config`). Notable design points, in case this needs revisiting once the finished course project lands:
     - **Transport history, in case this comes up again**: this package went through two failed Telegram-based designs before landing on MQTT. First, one shared bot for every machine — broken because a bot never receives, via `getUpdates`, messages it sent itself, so nothing ever round-tripped. Second, one bot per machine in a shared group with privacy mode disabled — still broken, because Telegram's Bot API silently never delivers one bot's messages to another bot regardless of privacy/admin settings (undocumented, confirmed by direct testing: a human's messages were delivered fine, a bot's never were). MQTT has no equivalent restriction — any client publishing to a topic is delivered to every other subscriber of that topic, including other bots/services — which is why the package now uses `paho-mqtt` (MQTT5, for its per-message "user properties") instead of a chat platform's API.
     - The listener starts from `GeminiLiveWorker.__init__` (not `main_basic.py`, to keep the "only touch `live_client_basic.py`" constraint) — idempotently, via a module-level flag in `mqtt_listener.py` — but `iniciar_rede_jarvis()` *always* re-registers the voice/frame callbacks on every call, since `GeminiLiveWorker` instances (and their live session) are discarded between calls; a stale callback would otherwise keep pointing at a dead session.
     - Unlike the earlier Telegram implementation, `mqtt_client.py`'s `publicar_*` functions are plain synchronous, thread-safe calls (paho-mqtt's `loop_start()` owns its own internal network thread) — no dedicated event loop or `run_coroutine_threadsafe`/futures dance is needed to call them from `comandos.py`, `visualizacao_remota.py`, or `transferencia_arquivos.py`. Don't reintroduce that complexity if extending this package.
     - Routing is envelope-based, not topic-based: every machine subscribes to the same three fixed shared topics (`jarvis/comandos` for JSON command/response envelopes, `jarvis/frames` and `jarvis/arquivos` for binary payloads with MQTT5 user-properties as metadata), and `TOKEN_REDE_JARVIS` + a `destino` field (checked against `NOME_MAQUINA`/`"todos"`) inside each message decide what gets processed — mirrors the very first (pre-Telegram-bug) design, since that filtering logic was always transport-agnostic.
     - Presence/online-status (`listar_maquinas_remotas`) is the one exception to shared topics: each machine has its own `jarvis/presenca/<NOME_MAQUINA>` topic (subscribed to in aggregate via the `jarvis/presenca/+` wildcard), and uses two MQTT-native mechanisms instead of a request/response round trip — a **retained** "online" message published right after connecting (so any machine that subscribes later still immediately gets everyone's last-known status, no polling needed), and a **Last Will** (`will_set`, configured before `connect()`) that the *broker itself* publishes as a retained "offline" message if a client's connection drops without a clean MQTT disconnect (crash, killed process, network loss — detected via the `keepalive` window, 60s here, so worst-case detection lag is ~1.5×that). `mqtt_listener.py` keeps an in-memory `_MAQUINAS_ONLINE` dict updated purely from these messages; `listar_maquinas_online()` never makes a network call, it just reads that dict. Verified for real against HiveMQ Cloud, including forcibly killing a raw socket (no clean disconnect) and confirming the broker published the Will and the peer's listener removed it from the list within the keepalive window.
     - `win11toast` (WinRT) **must never be imported at module load time** anywhere in this package — importing it before PySide6 has initialized COM in the same process reliably segfaults the interpreter. `notificacoes.py` imports it lazily inside each function for this reason; don't hoist that import to the top of the file.
     - `transferencia_arquivos.py`'s save-file dialog (`QFileDialog`, needed on the receiving end) runs on a background thread but must execute on the Qt GUI thread — it uses a `QObject` with a queued-connection `Signal` (`_PonteSalvarArquivo`) instantiated once, eagerly, from `GeminiLiveWorker.__init__` (i.e. the GUI thread) via `preparar_ponte_gui()`, so its thread affinity is correct.
     - `comandos.py`'s `capturar_tela` has no "just look at it in the chat" option the way Telegram did — the captured frame is delivered through the exact same path as a received file (`jarvis/arquivos`, notification + `QFileDialog`/timeout-to-`PASTA_TRANSFERENCIAS_PADRAO`), not injected into any Gemini session.
     - `visualizacao_remota.py` still runs its own dedicated background event loop (for the `MonitorTelaContinuo` capture cycle, independent of MQTT) — when scheduling a coroutine onto it via `run_coroutine_threadsafe`, never call `loop.stop()` as the coroutine's own last statement — the wrapping `concurrent.futures.Future`'s result-callback can lose the race against the loop stopping, causing the caller's `future.result()` to time out even though the coroutine finished fine. Stop the loop in a separate `call_soon_threadsafe(loop.stop)` after `future.result()` returns (see `visualizacao_remota.parar`).
     - Large file transfers via Google Drive need the *destination* machine's service-account email before sharing; since only its own credential file is known locally, the sender asks for it over the same MQTT channel (`tipo: "consulta_service_account"`) rather than requiring a manually-maintained machine→email mapping — this keeps "add a new machine later" working without touching other machines' config.

## Key constraints to preserve when editing

- The voice keyword authentication gate in the system prompt is a deliberate security/access-control feature of the assistant persona — don't strip it out during refactors.
- Audio playback must stay glitch-free: no `asyncio.sleep` was deliberately added inside the `reproduzir_audio` write loop (see comment in that method) — don't add pacing delays there.
- Vision, email, and memory functions are intentionally *not* auto-triggered by the model — the system prompt explicitly restricts them to explicit user requests, and for `enviar_email` specifically requires the recipient/subject/body to have been stated by the user rather than invented. Preserve these restrictions when adjusting `instrucao_sistema`.
- No file in this repo ever writes real emails during tests/dev — `mailer/email_sender.py`'s SMTP calls are only exercised against a real server when the user actually triggers it through a live call with real `.env` credentials.
- `rede_jarvis/comandos.py`'s `abrir_app` and `buscar_arquivo` must stay whitelist-only (`config.WHITELIST_APPS`, `config.PASTAS_PERMITIDAS_BUSCA`) — never execute an arbitrary command/path coming from an MQTT message, even though the message passed the shared-token check. Every message without the correct `TOKEN_REDE_JARVIS` is dropped silently (no reply), by design — don't add an error response for that case, it would confirm the channel's existence to a probing attacker.
- `rede_jarvis`'s Google Drive fallback path (large-file transfer): auth against a real Service Account was verified (connects fine, `client_email` reads correctly), but the upload+share+download+cleanup path itself is still untested end-to-end. Also, a real Service Account tested here came back with `storageQuota: {limit: "0", ...}` — service accounts on non-Workspace (personal) Google Cloud projects typically have no personal Drive storage, so `files().create()` may fail with a quota error even with everything else configured correctly. A Shared Drive (Workspace) the service account has access to would likely be needed; this hasn't been set up or tested.
