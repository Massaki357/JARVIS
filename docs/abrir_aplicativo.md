# jarvis/pacotes/abrir_aplicativo/ (substituiu abrir_app_local)

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/abrir_app_local/` — **REMOVED.** Replaced by `jarvis/pacotes/abrir_aplicativo/` (see the "Packages brought over from `JARVIS COMPLETO`" section below). Its `PASTAS_EXTRAS_APPS` support was carried over; its `dados/apps_conhecidos.json` cache and its `difflib`-based fuzzy matching were not (the replacement resolves names through Windows' own aliases and the Start Menu instead). The old code is still in git history if any of it is ever needed back.

     - `jarvis/pacotes/abrir_aplicativo/` — **replaced the `abrir_app_local` package, which was deleted** (explicit user decision when offered the choice between merging, coexisting, or replacing). Resolves a spoken name in four steps: fixed Windows aliases (Meu Computador, Explorador, Configurações, Calculadora, Painel de Controle, personal folders), Start Menu `.lnk`/`.url` shortcuts, `Get-StartApps` (Microsoft Store apps), and a fixed dictionary of known executables via `shutil.which`. It has no on-disk cache (the old one had `dados/apps_conhecidos.json`) — the first two steps already answer instantly. **A fifth step was added that did not exist in the course version**: `abrir_de_pastas_extras()` preserves `PASTAS_EXTRAS_APPS` from the deleted package (shallow scan — the folder itself plus one level of subfolders, never a deep `rglob`), because dropping it would silently lose portable programs for anyone who had that variable configured. `executar_comando` still always uses `subprocess.Popen(..., shell=False)`.

## Restrições a preservar ao editar

- `abrir_aplicativo`'s `PASTAS_EXTRAS_APPS` scan (`acoes.abrir_de_pastas_extras()`) must stay a shallow scan (the folder itself plus one level of subfolders) — don't switch it to an unbounded recursive walk (`rglob`), which could make a simple voice command take an unpredictably long time on a large folder tree. It must also stay the LAST of the five resolution steps: the four steps before it are what Windows itself already knows about, and they should always win.
