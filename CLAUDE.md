# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ALFRED is a Windows desktop voice assistant built with PySide6 and the Gemini Live API (`google-genai`). It streams microphone audio to Gemini in real time, plays back the spoken response, and can call a small set of tools (screen capture, continuous screen viewing, webcam capture, persistent memory, sending/reading email, remote commands to other ALFRED instances over Telegram, call termination) that the model triggers by voice. All conversation happens in Brazilian Portuguese, and all identifiers, comments, and UI strings in the codebase are in Portuguese — follow that convention when editing.

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
TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
TOKEN_REDE_JARVIS=<shared secret, same value on every machine>
NOME_MAQUINA=<this machine's name, e.g. "casa" or "loja">
TELEGRAM_CHAT_ID=<shared chat/group id all machines send/receive through>
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
   - Tool calls from Gemini (`resposta.tool_call`) are dispatched in `processar_chamada_de_funcao` by name: `analisar_tela` / `analisar_camera` (single-frame vision), `iniciar_visualizacao_continua` / `parar_visualizacao_continua` (continuous screen streaming), `enviar_email` (SMTP) / `ler_emails` (IMAP, `pasta` param constrained to the `INBOX`/`SPAM` enum), `enviar_comando_remoto` / `responder_permissao_remota` (remote machines over Telegram — see the `rede_jarvis` bullet below), `salvar_memoria` / `listar_memorias` / `esquecer_memoria` (memory), `encerrar_chamada` (ends the call after a short delay so the goodbye line finishes playing, via `solicitou_encerramento` signal back to the UI). Adding a new voice tool means: add a `types.FunctionDeclaration` to the `tools` list, add a branch in `processar_chamada_de_funcao`, and update `instrucao_sistema` with usage rules.
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
   - `rede_jarvis/` — a self-contained package for remote command/control between machines running ALFRED, using a shared Telegram bot as the transport (no VPN/relay server). Deliberately isolated from the rest of the app: `gemini/live_client_basic.py` only imports the package, adds the `enviar_comando_remoto`/`responder_permissao_remota` `FunctionDeclaration`s, dispatches to `rede_jarvis.enviar_comando_remoto`/`rede_jarvis.responder_permissao_por_voz`, and has two small session-glue methods (`_falar_rede_jarvis`, `_receber_frame_remoto`) that adapt the package's abstract callbacks to this specific Gemini session (`send_client_content`/`send_realtime_input`) — no other business logic lives outside the package. See `rede_jarvis/__init__.py`'s docstrings for the full module breakdown (`telegram_client`, `telegram_listener`, `comandos`, `visualizacao_remota`, `transferencia_arquivos`, `permissoes`, `notificacoes`, `config`). Notable design points, in case this needs revisiting once the finished course project lands:
     - The listener starts from `GeminiLiveWorker.__init__` (not `main_basic.py`, to keep the "only touch `live_client_basic.py`" constraint) — idempotently, via a module-level flag in `telegram_listener.py` — but `iniciar_rede_jarvis()` *always* re-registers the voice/frame callbacks on every call, since `GeminiLiveWorker` instances (and their live session) are discarded between calls; a stale callback would otherwise keep pointing at a dead session.
     - **Known limitation, not silently "fixed":** Telegram's `getUpdates` only supports one active poller per bot token; multiple machines' listeners polling the same bot concurrently can occasionally 409/miss updates. The listener uses short-timeout polling + retry to shrink (not eliminate) that window — see the comment in `telegram_listener._loop_principal`. A relay/webhook server would remove this but was explicitly out of scope ("sem VPN").
     - `win11toast` (WinRT) **must never be imported at module load time** anywhere in this package — importing it before PySide6 has initialized COM in the same process reliably segfaults the interpreter. `notificacoes.py` imports it lazily inside each function for this reason; don't hoist that import to the top of the file.
     - `transferencia_arquivos.py`'s save-file dialog (`QFileDialog`, needed on the receiving end) runs on a background thread but must execute on the Qt GUI thread — it uses a `QObject` with a queued-connection `Signal` (`_PonteSalvarArquivo`) instantiated once, eagerly, from `GeminiLiveWorker.__init__` (i.e. the GUI thread) via `preparar_ponte_gui()`, so its thread affinity is correct.
     - When scheduling a coroutine onto `visualizacao_remota.py`'s dedicated background event loop via `run_coroutine_threadsafe`, never call `loop.stop()` as the coroutine's own last statement — the wrapping `concurrent.futures.Future`'s result-callback can lose the race against the loop stopping, causing the caller's `future.result()` to time out even though the coroutine finished fine. Stop the loop in a separate `call_soon_threadsafe(loop.stop)` after `future.result()` returns (see `visualizacao_remota.parar`).
     - Large file transfers via Google Drive need the *destination* machine's service-account email before sharing; since only its own credential file is known locally, the sender asks for it over the same Telegram channel (`tipo: "consulta_service_account"`) rather than requiring a manually-maintained machine→email mapping — this keeps "add a new machine later" working without touching other machines' config.

## Key constraints to preserve when editing

- The voice keyword authentication gate in the system prompt is a deliberate security/access-control feature of the assistant persona — don't strip it out during refactors.
- Audio playback must stay glitch-free: no `asyncio.sleep` was deliberately added inside the `reproduzir_audio` write loop (see comment in that method) — don't add pacing delays there.
- Vision, email, and memory functions are intentionally *not* auto-triggered by the model — the system prompt explicitly restricts them to explicit user requests, and for `enviar_email` specifically requires the recipient/subject/body to have been stated by the user rather than invented. Preserve these restrictions when adjusting `instrucao_sistema`.
- No file in this repo ever writes real emails during tests/dev — `mailer/email_sender.py`'s SMTP calls are only exercised against a real server when the user actually triggers it through a live call with real `.env` credentials.
- `rede_jarvis/comandos.py`'s `abrir_app` and `buscar_arquivo` must stay whitelist-only (`config.WHITELIST_APPS`, `config.PASTAS_PERMITIDAS_BUSCA`) — never execute an arbitrary command/path coming from a Telegram message, even though the message passed the shared-token check. Every message without the correct `TOKEN_REDE_JARVIS` is dropped silently (no reply), by design — don't add an error response for that case, it would confirm the bot's existence to a probing attacker.
- `rede_jarvis`'s Google Drive fallback path (large-file transfer) is implemented but untested against real Service Account credentials — nobody in this project has set one up yet. Don't assume it's been exercised end-to-end; verify against a real `GOOGLE_SERVICE_ACCOUNT_JSON` before relying on it.
