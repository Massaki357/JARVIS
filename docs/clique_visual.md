# jarvis/pacotes/clique_visual/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/clique_visual/` — `clicar_elemento_visual`. **Was a native tool in the course client; became a package here.** Two things make it different from every other package: (1) it is the **only package that imports from another package** (`controle_mouse.acoes.mover_e_clicar`) — deliberate, one-directional, because both halves came from the same course mouse module and a second copy of the cursor-moving `ctypes` code would drift out of sync; (2) its `despachar()` **captures the screen internally**, which is why it's listed in `TOOLS_QUE_CAPTURAM_SOZINHAS` and the client holds `_mutex_funcao_visual()` around its whole dispatch (see below). The locator itself lives in `jarvis/servicos/visao/localizador_clique.py` (shared vision infra, next to the other capture functions), not inside the package — it blocks a sensitive/destructive target by keyword (`TERMOS_BLOQUEADOS`: excluir, apagar, formatar, comprar, pagar, transferir, instalar, "executar como administrador"...) **before even capturing the screen**, and refuses any result below `CONFIANCA_MINIMA` (0.78).
