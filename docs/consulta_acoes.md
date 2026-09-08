# jarvis/pacotes/consulta_acoes/

> Contexto detalhado deste módulo, extraído do CLAUDE.md raiz. Leia antes de editar arquivos desta área.

> Faz parte dos pacotes trazidos do `JARVIS COMPLETO` (pasta `actions/` do curso). Ver docs/INTEGRATION.md, seção "Pacotes vindos do JARVIS COMPLETO", para a tabela completa.

## Arquitetura e decisões de design

- `jarvis/pacotes/consulta_acoes/` — `consultar_cotacao_acao` and `consultar_historico_acao` (Twelve Data). In the course this existed only for the OpenAI Realtime provider; here it's an ordinary package, so it works in **both** voice brains, per the user's explicit request ("adicione o Twelve Data para os 2"). Two changes from the course: `TWELVE_DATA_API_KEY` moved from `core/config.py` to the package's own `config.py` (per-package `load_dotenv()` convention), and the dict/list → string formatting lives in `__init__.py`, so `acoes.py` stays byte-identical to the original (it was written to be JSON-serialized straight into an OpenAI tool output; this project's contract requires `despachar()` to return a string). `acoes.py` deliberately never interpolates the `requests` exception or the request URL into an error message — both contain the full query string, and therefore the API key in plain text. **Verified against the real API**: a batch quote for `["AAPL", "MSFT"]` came back with both tickers in one call, a 10-candle daily history returned with the period trend computed correctly, and an invalid ticker produced the Twelve Data 404 message as text rather than an exception.
