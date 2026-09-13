# jarvis/pacotes/pesquisa_web/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/pesquisa_web/` — `pesquisar_informacao_atual`, an invisible DuckDuckGo search (`ddgs`) that opens no window and never steals focus. The point of the module is the **local filter that runs before any network access**: `avaliar_necessidade_pesquisa()` checks currency markers, dynamic subjects, and changing job titles, and then a list of stable-question patterns that *block* the search. `despachar()` calls `pesquisar_informacao_atual()`, which runs that filter itself and returns `resposta_sem_pesquisa()` when the question doesn't need current data — **don't duplicate that decision in a client**. 60s in-memory cache, thread-safe. **Verified against the real service**: a currency-quote question returned real formatted results, and the identical follow-up question came back from the cache instead of hitting the network again. The filter itself was verified both ways on seven phrasings — four that must search (cotação, current officeholder, match score, forecast) and three that must not (o que é Python, quem foi Einstein, como funciona um motor).
