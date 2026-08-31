---
name: novo-pacote-jarvis
description: Passo a passo para criar um novo pacote de tools isolado no projeto jarvis, seguindo o contrato obter_function_declarations()/despachar() documentado em INTEGRATION.md.
---

# Criar um novo pacote de tools isolado

Use este passo a passo sempre que uma nova capacidade for adicionada ao jarvis por voz
(ex: um novo provedor de LLM, uma nova integração de hardware, um novo canal de
comunicação). O objetivo é que `gemini/live_client_basic.py` — um arquivo `_basic`,
temporário — nunca ganhe lógica de negócio nova, só os três pontos de contato do
contrato padrão.

Antes de começar, releia `INTEGRATION.md` — ele é a fonte da verdade sobre o contrato e
pode ter mudado desde a última vez que você criou um pacote.

## 1. Estrutura do pacote

Crie uma pasta nova na raiz do projeto (irmã de `rede_jarvis/`, `casa_inteligente/`,
`delegacao_ia/`), nunca dentro de `gemini/`, `ui/` ou outro módulo existente. Dentro
dela, no mínimo:

- `config.py` — carrega `.env` via `load_dotenv()` próprio (não reaproveite
  `core/config.py` — cada pacote é decoupled de propósito, pra poder ser copiado pra
  outro projeto como está). Nenhuma credencial hardcoded, sempre `os.getenv(...)`.
- O(s) módulo(s) com a lógica de negócio em si (ex: um `cliente.py` fino pro SDK/API
  externa, mais um módulo com as funções de ação).
- `__init__.py` — só a casca do contrato (seção 2 abaixo), sem lógica de negócio.

Se o pacote precisar bloquear em I/O de rede/disco, tudo bem — `despachar()` já é
chamado via `asyncio.to_thread` pelo lado do cliente, então pode ser síncrono.

## 2. O contrato: `obter_function_declarations()` e `despachar()`

No `__init__.py` do pacote:

```python
from google.genai import types
from . import roteador_ou_logica_do_pacote

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="nome_da_tool",
        description="...",
        parameters=types.Schema(
            type="OBJECT",
            properties={...},
            required=[...],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre uma
# string, pronta pro Jarvis falar). Se não reconhecer, retorna None —
# quem chama tenta o próximo pacote da lista.
def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "nome_da_tool":
        return roteador_ou_logica_do_pacote.executar(argumentos)

    return None
```

Regras do contrato (não são negociáveis, ver `casa_inteligente`/`delegacao_ia` como
referência de pacotes sem wiring extra, e `rede_jarvis` como referência de pacote com
wiring extra):

- Prefira **uma tool genérica** com um parâmetro que decide o comportamento (ex:
  `controlar_dispositivo_casa(dispositivo, acao)`, `delegar_tarefa(tipo_tarefa,
  conteudo)`) a várias tools finas, quando as ações são da mesma família — deixa o
  `instrucao_sistema` mais simples de manter.
- `despachar()` **nunca lança exceção** para o chamador — capture erros internamente e
  retorne uma string em português explicando o que aconteceu (mesma convenção de
  `mailer/email_sender.py`, `memory_manager.py`, `casa_inteligente/tuya_client.py`). O
  retorno vira fala do Jarvis.
- `despachar()` retorna `None` — não lança `KeyError`/etc — quando `nome_funcao` não é
  reconhecido, para o loop de despacho genérico poder tentar o próximo pacote.
- Se o pacote expõe uma ação sensível (executar comando, abrir app, acessar
  arquivo/rede a partir de uma entrada externa), ela **precisa passar por uma
  whitelist** definida no `config.py` do próprio pacote — nunca aceitar
  comando/caminho/nome arbitrário vindo de fora. Ver `tuya-troubleshooting.md` não se
  aplica aqui; a referência é `rede_jarvis/config.py` (`WHITELIST_APPS`,
  `PASTAS_PERMITIDAS_BUSCA`).

## 3. Wiring no cliente (`gemini/live_client_basic.py`)

Exatamente três pontos de contato — nada além disso deve mudar neste arquivo:

1. **Import**, junto dos outros imports de pacote:
   ```python
   import nome_do_pacote
   ```
2. **Uma linha em `PACOTES_REGISTRADOS`**:
   ```python
   PACOTES_REGISTRADOS = [
       rede_jarvis,
       casa_inteligente,
       delegacao_ia,
       nome_do_pacote,
   ]
   ```
   O loop de despacho genérico e a extensão de `tools` já iteram essa lista — não
   precisa tocar em mais nada ali.
3. **`instrucao_sistema`**: adicione uma seção curta explicando pro modelo quando usar
   a(s) tool(s) nova(s), com exemplos concretos de frase que USAM e que NÃO usam a
   tool, na mesma densidade das seções `# DELEGAÇÃO DE TAREFAS` / `# CASA INTELIGENTE`
   / `# REDE JARVIS` já existentes.

Se o pacote precisar de **wiring extra** (callbacks de sessão, inicialização em
background, uma ponte pra GUI thread) — como `rede_jarvis` precisa — documente o
wiring extra em `INTEGRATION.md` na seção "Wiring extra por pacote" (com o trecho de
código pronto pra copiar), e implemente só o mínimo necessário no `__init__` do
worker. Consulte a seção de `rede_jarvis` em INTEGRATION.md como modelo antes de
inventar um mecanismo novo — a maioria dos casos (ação HTTP pontual, sem estado)
não precisa de wiring extra nenhum.

## 4. Atualize a documentação (não é opcional)

- **`INTEGRATION.md`**: adicione o pacote novo ao trecho "pronto para copiar" (import +
  `PACOTES_REGISTRADOS`) e, se houver wiring extra, uma subseção nova em "Wiring extra
  por pacote".
- **`CLAUDE.md`**: adicione um item na lista de "Supporting modules" (seção
  Architecture) descrevendo o que o pacote faz, decisões não óbvias e qualquer
  limitação conhecida — no mesmo nível de detalhe dos pacotes existentes. Se o pacote
  introduzir uma nova variável de `.env`, documente em "Setup and running".

## 5. Antes de considerar terminado

- Compile os arquivos novos (`python -m py_compile`) e o `live_client_basic.py`
  editado.
- Rode o app (`python main_basic.py`), confirme que não crasha na inicialização e que
  `PACOTES_REGISTRADOS` carrega sem erro.
- Teste a tool nova por voz (ou via chamada direta a `despachar()` num script de teste)
  contra a API/serviço real — nunca declare uma integração externa como "funcionando"
  sem ter confirmado ao vivo (ver `tuya-troubleshooting.md` para um exemplo do que dá
  errado quando isso não é feito).
