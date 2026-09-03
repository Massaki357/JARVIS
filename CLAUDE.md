# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ALFRED is a Windows desktop voice assistant built with PySide6 and the Gemini Live API (`google-genai`). It streams microphone audio to Gemini in real time, plays back the spoken response, and can call a large set of tools that the model triggers by voice: screen/webcam capture, visual element location + clicking, Windows desktop file management, opening apps/system resources, browser search, YouTube playback, invisible "current info" web search, mouse control, typing into the active field, a persistent local agenda, persistent memory, and call termination. All conversation happens in Brazilian Portuguese, and all identifiers, comments, and UI strings in the codebase are in Portuguese — follow that convention when editing.

This is a learning/course project (`[CURSO]` comments throughout explain Python/Qt/asyncio concepts for the author). Comments are intentionally verbose for teaching purposes; match the existing density if adding to files that already have it, but don't add new `[CURSO]`-style comments yourself.

For a complete, file-by-file / function-by-function breakdown of the codebase, see **`ARCHITECTURE.md`**. This file focuses on the overall flow and the constraints to preserve when editing.

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
```

`vision/click_locator.py` optionally reads `GEMINI_VISION_MODEL` from the environment too (defaults to `gemini-3.1-flash-lite`) for the separate visual-element-locator model call.

## Architecture

Four-layer flow, entry point `main.py`:

1. **UI layer** — `ui/main_window.py` (`MainWindow`, `QMainWindow`) + `ui/alfred_visualizer.py` (`AlfredVisualizer`, `QWidget`).
   - `MainWindow` builds the window (side panel with call/analyze-screen/analyze-camera buttons + event log, main panel hosting the visualizer) with an inline QSS stylesheet. Owns a single `GeminiLiveWorker` instance (`self.live_worker`), created fresh on each call and discarded when the call ends. Wires every worker signal: `status_recebido`, `erro_recebido`, `chamada_encerrada`, `solicitou_encerramento`, `solicitou_reconexao`, `session_handle_atualizado`, `nivel_audio`.
   - `MainWindow` also tracks `session_handle` (Gemini Live resumption token) and `reconectar_automaticamente`/`encerramento_manual` flags, so a dropped/renewed connection (server `GoAway`, network error) reconnects automatically **without losing conversation context**, while a manual or voice-requested hangup does not reconnect and clears the handle.
   - `AlfredVisualizer` is a hand-drawn `QPainter` animated orb/rings visualizer reacting to call state and voice volume. It caches the expensive background/sphere as `QPixmap`s and only redraws the cheap reactive layers (glow, rings, audio bar, status text) each frame, with adaptive FPS (6 idle / 15 active / 20 speaking) to keep CPU usage low. Public API used by `MainWindow`: `definir_status`, `definir_ativo`, `definir_nivel_audio`.

2. **Gemini Live worker** — `gemini/live_client.py` (`GeminiLiveWorker`, a `QThread`). This is the core of the app:
   - Runs its own `asyncio` event loop (`run()` → `asyncio.run(self.executar())`) so the Qt UI thread never blocks.
   - Opens a `client.aio.live.connect(...)` session against `GEMINI_LIVE_MODEL`, with `session_resumption` and `context_window_compression` configured, and runs three concurrent asyncio tasks: `enviar_microfone` (mic → Gemini via `sounddevice.RawInputStream`), `receber_audio` (Gemini → playback queue + tool-call dispatch + session-renewal/resumption handling), `reproduzir_audio` (queue → speakers via `sounddevice.RawOutputStream`). If any of the three tasks dies unexpectedly, the whole session is torn down rather than limping along silently.
   - Echo prevention: while `self.alfred_falando` is `True` (assistant is speaking), microphone input is dropped, both at the sounddevice callback level and again when pulling from the queue, plus a queue flush (`limpar_fila_microfone`) whenever new assistant audio starts. A separate `silenciar_audio_ate_fim_turno` flag discards the model's audio reply for actions meant to happen silently (page scroll, typing into a field, visual click).
   - `instrucao_sistema` (system prompt) defines ALFRED's identity/personality and, critically, a voice-based authentication gate: the app only responds to commands after the user speaks a secret keyword ("Coisa" — also documented in README.MD). **Never remove or weaken this auth logic without being asked.** It also injects the current local date/time (for interpreting "hoje"/"amanhã" in agenda requests) and the persistent-memory context (`contexto_memorias()`) from `memory/memory_manager.py`.
   - Session renewal: the server can send a `GoAway` before closing the WebSocket; the worker detects it, emits `solicitou_reconexao` (not treated as an error), and lets the UI reopen a new connection using the latest `session_handle` (kept in sync via the `session_handle_atualizado` signal) so the conversation isn't lost.
   - Tool calls from Gemini (`resposta.tool_call`) are dispatched in `processar_chamada_de_funcao` by name, one `elif` branch per tool, each routed to a function in `actions/`, `vision/`, or `memory/`. See **`ARCHITECTURE.md`** for the full tool → function table (desktop file ops, app launching, browser/YouTube, invisible web search, mouse control, visual-element click, typed text, agenda, memory, call termination, screen/camera analysis). Adding a new voice tool means: add a `types.FunctionDeclaration` to the `tools` list, add a branch in `processar_chamada_de_funcao` (most non-visual ones should go through `executar_funcao_local(funcao, *args, timeout=...)`, which runs the sync function in a thread with a timeout), and update `instrucao_sistema` with usage rules.
   - Repeated/near-simultaneous vision-tool calls (`analisar_tela`/`analisar_camera`) are throttled via `executando_funcao_visual` (mutex) and `COOLDOWN_FUNCAO_VISUAL` (8s per-function debounce). The captured image is queued in `imagem_visual_pendente` and only sent to Gemini after the tool response is acknowledged (`send_tool_response`), to keep the Live protocol event order correct. The "ANALISAR TELA"/"ANALISAR CÂMERA" UI buttons use a *separate* code path (`solicitar_analise_tela`/`enviar_tela_para_gemini` and camera equivalents) that sends the image directly via `send_client_content`, bypassing the tool-call mechanism entirely.

3. **Actions layer** — `actions/` (all new). Each file is an independent Windows-automation module invoked only from `gemini/live_client.py`'s tool dispatch, never directly by the user:
   - `file_actions.py` — Desktop-only file management (create folder, list, organize-by-type, copy/cut/paste via an in-memory "clipboard" dict, rename). All paths are validated to stay inside the Desktop folder; **never deletes anything, never overwrites an existing item**.
   - `app_actions.py` — opens apps/system resources via a 4-step fallback chain: hardcoded special aliases → Start Menu shortcut search (`.lnk`/`.url`) → `Get-StartApps` PowerShell lookup (covers Store apps) → known-executable fallback (`shutil.which`). Always uses `subprocess.Popen(..., shell=False)`.
   - `browser_actions.py` — opens a Google search or a YouTube video (scrapes the first `videoId` out of the YouTube results HTML via regex, no Selenium/Playwright/PyWhatKit) in the default browser.
   - `web_search.py` — *invisible* current-info search (no browser window opens). A fast local filter (`avaliar_necessidade_pesquisa`) decides whether a query actually needs live data before ever hitting the network; only then does `pesquisar_informacao_atual` query `ddgs` (DuckDuckGo), with a 60s in-memory cache.
   - `mouse_actions.py` — scroll/click/move via raw Windows `user32.dll` calls through `ctypes` (no `pyautogui`).
   - `text_actions.py` — types into the currently focused Windows field by writing to the real clipboard (`GlobalAlloc`/`SetClipboardData`) and simulating `Ctrl+V` via `keybd_event`.
   - `agenda_actions.py` — the local persistent agenda (create/list/cancel appointments), backed by `memory/agenda.json` with the same threading-lock + atomic-write pattern as `memory/memory_manager.py`. **This file, not `memory/memory_manager.py`, owns the agenda.**

4. **Supporting modules**:
   - `core/config.py` — loads `.env` via `python-dotenv`, exposes `GEMINI_API_KEY`, `GEMINI_LIVE_MODEL`, `GEMINI_VOICE`. Available model/voice options are listed in comments here — swap the active value rather than adding new config plumbing.
   - `vision/screen_capture.py` / `vision/camera_capture.py` — each exposes one function (`capturar_tela_bytes` / `capturar_camera_bytes`) that captures a single frame (via `mss` / `cv2`) and returns in-memory JPEG bytes (via `Pillow`). No files are ever written to disk. These bytes get sent to Gemini as `inline_data` parts alongside a per-call text instruction that tells the model to only use the freshly sent image.
   - `vision/click_locator.py` — the visual element locator behind the `clicar_elemento_visual` tool. Blocks sensitive/destructive-sounding targets *before* capturing anything (`TERMOS_BLOQUEADOS`: excluir, apagar, deletar, formatar, comprar, pagar, transferir, instalar, desinstalar, "executar como administrador", etc.), then captures the primary monitor, asks a separate Gemini model (`GEMINI_VISION_MODEL`) for normalized (0–1000) coordinates + confidence via a structured JSON schema, and refuses to act below `CONFIANCA_MINIMA` (0.78). Returns absolute screen coordinates that `live_client.py` feeds to `actions.mouse_actions.mover_e_clicar`. This confidence gate + blocked-terms list is the main safety mechanism for voice-guided clicking — preserve it.
   - `memory/memory_manager.py` — persistent memory store backed by `memory/memory.json` (created on demand), guarded by a `threading.Lock` for read/write safety and atomic writes (write to `.tmp`, then `Path.replace`). Public API: `salvar_memoria`, `listar_memorias`, `esquecer_memoria`, `contexto_memorias` (injected into the system prompt at session start). Enforces `MAXIMO_MEMORIAS` (50 entries) and `MAXIMO_CARACTERES` (200 chars/entry), de-duplicates via accent/case-insensitive normalization (`_normalizar_texto`), and refuses bulk-delete phrases like "esquecer tudo" as a safety guard. `esquecer_memoria` resolves a reference by exact ID, then exact text match, then unique partial match (asks for disambiguation if multiple candidates match).
   - `memory/agenda.json` — data file (not code) managed by `actions/agenda_actions.py`; empty by default (`{"versao": 1, "eventos": []}`), capped at 20 upcoming events.

## Key constraints to preserve when editing

- The voice keyword authentication gate in the system prompt is a deliberate security/access-control feature of the assistant persona — don't strip it out during refactors.
- Audio playback must stay glitch-free: no `asyncio.sleep` was deliberately added inside the `reproduzir_audio` write loop (see comment in that method) — don't add pacing delays there.
- Vision, memory, agenda, mouse, file, app, browser and search functions are intentionally *not* auto-triggered by the model — the system prompt explicitly restricts them to explicit user requests. Preserve that restriction when adjusting `instrucao_sistema`.
- `actions/file_actions.py` must never delete or overwrite anything, and must never operate outside the Desktop folder — this is enforced both in code (path validation, `exist_ok=False`, existence checks) and in the system prompt ("Nunca exclua arquivos ou pastas... Nunca sobrescreva... Nunca formate").
- `vision/click_locator.py`'s blocked-terms list and confidence threshold (0.78) are the safety gate against destructive voice-guided clicks — don't lower the threshold or shrink the blocked-terms list without being asked.
- Session resumption (`session_handle`) must keep being cleared on any user-initiated or voice-initiated hangup, and preserved across automatic `GoAway`-triggered reconnects — mixing these up breaks either "clean start" or "seamless reconnect" behavior.
