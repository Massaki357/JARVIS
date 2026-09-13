# jarvis/pacotes/controle_mouse/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/controle_mouse/` — `rolar_pagina`, `clicar_mouse`, `duplo_clique_mouse`, `clique_direito_mouse`, via `user32.dll` through `ctypes` (no `pyautogui`). **`mover_e_clicar()` is deliberately NOT exposed as a tool** — a voice-dictated "click at x,y" would be a blind click with none of the two protections the visual locator provides; it exists only for `clique_visual` to call after a target has been approved.

## Restrições a preservar ao editar

- **`controle_mouse.acoes.mover_e_clicar` must never become a voice-callable tool.** It is only ever called by `clique_visual`, and only after `localizador_clique` has approved the target — a spoken "click at x,y" would be a blind click with neither the blocked-terms list nor the confidence threshold protecting it. The same goes for the locator's own guards: `TERMOS_BLOQUEADOS` is checked *before* the screen is even captured, and `CONFIANCA_MINIMA` (0.78) must not be lowered to make the tool "work more often".
