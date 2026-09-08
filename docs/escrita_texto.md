# jarvis/pacotes/escrita_texto/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/escrita_texto/` — `escrever_no_campo_ativo`, which puts the text on the **real** Windows clipboard (`GlobalAlloc`/`SetClipboardData`, `CF_UNICODETEXT`) and then simulates Ctrl+V. That preserves accents and long text far more reliably than key-by-key simulation, at the cost of replacing whatever the user had on their clipboard — the course's original behavior, kept. 10,000-character safety limit.
