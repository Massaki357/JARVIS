# jarvis/pacotes/agenda/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/agenda/` — `criar_evento_agenda`, `listar_agenda`, `cancelar_evento_agenda`. This package, not `memoria_obsidian`, is the entire calendar. Atomic writes (`.tmp` + `fsync` + `Path.replace`) and a `threading.Lock`, both from the original. **One change from the course**: the file moved from `memory/agenda.json` to `dados/agenda.json`, via `jarvis/caminhos.py` — no module in this project writes state next to its own code or counts `.parent` hops. Refuses past dates and exact duplicates, caps at `MAXIMO_EVENTOS` (20), auto-recovers from a missing/corrupt/malformed JSON file, and asks for disambiguation instead of guessing which event to cancel. **These functions create no alarms** — the prompt says so explicitly, so the model never promises one.
