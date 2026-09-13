# jarvis/pacotes/arquivos_area_trabalho/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/arquivos_area_trabalho/` — 8 tools for Desktop files (`criar_pasta_area_trabalho`, `listar_area_de_trabalho`, `organizar_area_de_trabalho_basico`, `copiar_item_area_trabalho`, `recortar_item_area_trabalho`, `colar_item_area_trabalho`, `renomear_item_area_trabalho`, `cancelar_transferencia_area_trabalho`). `acoes.py` is a literal copy of `actions/file_actions.py`. **The module's central protection is that every path goes through `_esta_dentro_da_area`/`_resolver_caminho_relativo`**, which reject anything outside the Desktop — verified live with `../../..` traversal. Copy/cut are two-step: they only record the item in an in-memory `_AREA_TRANSFERENCIA` (not the real Windows clipboard), and nothing moves until `colar_item_area_trabalho`. **No function in this file deletes anything** (verified: no `unlink`/`rmtree`/`os.remove` anywhere in it), and nothing ever overwrites an existing item.

## Restrições a preservar ao editar

- **`arquivos_area_trabalho` must never gain a function that deletes or overwrites.** Every path in `acoes.py` goes through `_esta_dentro_da_area`/`_resolver_caminho_relativo` (which reject anything outside the Desktop), every create uses `exist_ok=False`, and every paste/rename checks `destino.exists()` first. There is no `unlink`/`rmtree`/`os.remove` anywhere in that file and there must not be one — this is the module's whole security model, inherited from the course project and reinforced in the prompt's `## SEGURANÇA DAS AÇÕES LOCAIS` section.
