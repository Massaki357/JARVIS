# jarvis/pacotes/navegador_web/ (substituiu navegador_jarvis)

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/navegador_jarvis/` — **REMOVED.** Replaced by `jarvis/pacotes/navegador_web/` (see the "Packages brought over from `JARVIS COMPLETO`" section below). It drove a real Chromium through Playwright's async API in a persistent session, which is what made `pausar_musica`/`retomar_musica` possible; those two tools are gone with it, and `playwright` came out of `requirements.txt`. If browser *control* (as opposed to just opening a URL) is ever wanted again, that package's design — dedicated background thread with its own loop, self-healing session, `video.paused` checked before pressing "k" — is worth recovering from git history rather than redesigning.

     - `jarvis/pacotes/navegador_web/` — **replaced the `navegador_jarvis` package, which was deleted** (same explicit decision). `pesquisar_no_navegador` opens a Google search in the default browser; `tocar_no_youtube` fetches the YouTube results page over plain HTTP (`urllib`), extracts the first `videoId` by regex, and opens `/watch?v=...&autoplay=1` in the default browser. **`pausar_musica`/`retomar_musica` are gone with it** — those only worked because the old package drove its own persistent Playwright page, and there is no page under our control any more; the prompt's `## NAVEGADOR E YOUTUBE` section tells the model this explicitly ("não existe pausar nem retomar, então nunca prometa isso"). The `playwright` dependency was removed from `requirements.txt` in the same pass. Still never executes JavaScript and never navigates to a URL built from unvalidated text: the Google query goes through `quote_plus`, and the video URL is only ever built from a regex-validated 11-character ID.

## Restrições a preservar ao editar

- `navegador_web` must never execute arbitrary JavaScript or navigate to a URL constructed from unvalidated user text — an explicit user requirement carried over from the `navegador_jarvis` package it replaced. The two sanctioned URL shapes are the Google search built with `quote_plus`, and `youtube.com/watch?v=<id>` where `<id>` came from the `"videoId":"([a-zA-Z0-9_-]{11})"` regex — never a URL taken verbatim from spoken text.
- If `tocar_no_youtube` starts opening the results page instead of a video, the regex in `navegador_web/acoes.py::_extrair_video_id` stopped matching YouTube's current HTML — re-verify it against a real fetched results page before changing it, don't guess a new pattern from memory. The fallback (open the normal results page) is intentional and must stay: it always resolves to something usable.
