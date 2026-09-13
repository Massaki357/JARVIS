# jarvis/servicos/agentes/ — a camada única de chamada de agente (LangChain)

> Contexto detalhado deste módulo. Leia antes de editar arquivos desta área ou de escrever qualquer código novo que consulte uma LLM.

## O que é

Todo lugar do ALFRED que fala com uma LLM **de texto ou de visão** passa por aqui. É o LangChain embrulhado num contrato só, em português, com o mesmo formato de entrada e de saída para os cinco provedores em uso: **Gemini, OpenAI, Groq, Cerebras e Mistral**.

```python
from jarvis.servicos import agentes

resposta = agentes.executar(
    agentes.PedidoAgente(
        provedor="groq",                  # gemini | openai | groq | cerebras | mistral
        modelo=config.MODELO_GROQ,
        api_key=config.GROQ_API_KEY,      # SEMPRE do config.py de quem chama
        texto=pergunta,
        timeout=config.TIMEOUT_SEGUNDOS,  # em SEGUNDOS, sempre
    )
)

if not resposta.sucesso:
    return False, f"Não deu certo: {resposta.erro}"

return True, resposta.texto
```

Com imagem é o mesmo pedido com `imagem=<bytes JPEG>`. Com ferramentas, `ferramentas=<esquemas>` e a resposta em `resposta.primeira_chamada()`. Com JSON, `json_esperado=True` (ou `esquema_resposta=<dict>`) e o dicionário já decodificado em `resposta.dados`. **Nenhum desses casos tem formato próprio**: é sempre `PedidoAgente` entrando e `RespostaAgente` saindo, e `executar()` **nunca levanta exceção**.

## Arquivos

| arquivo | papel |
|---|---|
| `agente.py` | `PedidoAgente`, `RespostaAgente`, `PoliticaRepeticao`, `ChamadaFerramenta`, `UsoTokens` e `executar()` — o contrato |
| `modelos.py` | `criar_modelo()`: provedor → chat model do LangChain, com cache, import adiado e os pisos/esquisitices de cada API |
| `mensagens.py` | monta `SystemMessage`/`HumanMessage`/`AIMessage`, incluindo o bloco de imagem e a conversão do histórico `{"role", "content"}` |
| `ferramentas.py` | `FunctionDeclaration` (o formato que todo pacote já expõe) → dict de tool do `bind_tools()`; também é o dono de `normalizar_esquema` |
| `erros.py` | classifica a exceção do SDK em `LIMITE` / `TEMPO` / `AUTENTICACAO` / `FERRAMENTA_INDEVIDA` / `DESCONHECIDO`, e calcula a espera antes de repetir |

## O que passou a usar a camada

- `jarvis/pacotes/delegacao_ia/provedores.py` — os quatro provedores de texto
- `jarvis/roteamento_hierarquico/roteador.py` — as duas etapas, com tool calling na etapa 2
- `jarvis/pacotes/identificacao_visual/` — `gemini_vision_client.py` e `mistral_vision_client.py`
- `jarvis/pacotes/descricao_visual/cliente_visao.py` — os dois provedores viraram um caminho só
- `jarvis/pacotes/memoria_obsidian/consolidacao.py` — `_chamar_modelo_texto`
- `jarvis/servicos/visao/localizador_clique.py` — inclusive o esquema de resposta estruturada
- `jarvis/nucleo/perfis/geracao.py` — indiretamente, via `delegacao_ia`

## O que NÃO usa a camada, de propósito

**Os três cérebros de voz** (`jarvis/cerebro/gemini/`, `openai_realtime/`, `voz_local/`). Não são chamadas de pedido-e-resposta: são sessões de **áudio bidirecional em tempo real**, com interrupção, VAD, transcrição incremental e retomada de sessão. O LangChain não modela esse tipo de sessão, e reescrevê-los por cima dela significaria reimplementar o protocolo dos dois à mão, por baixo de uma abstração que não o representa. Eles ganham com a camada de outro jeito: toda ferramenta que despacham e que por sua vez consulta outra LLM atravessa um caminho só.

**As integrações HTTP que não são LLM**: `identificacao_planta` (Pl@ntNet — API de catálogo botânico, sem prompt nenhum) e `pesquisa_web` (ddgs).

## Decisões de design

- **Timeout é obrigatório, em segundos, sem exceção.** Não existe caminho que construa um modelo sem timeout. Antes desta camada, o mesmo projeto tinha clientes do Gemini contando em **milissegundos** (`HttpOptions`) e clientes de `requests` contando em segundos, e mais de uma trava silenciosa deste projeto nasceu de um cliente sem timeout nenhum — `memoria_obsidian/consolidacao.py` e `localizador_clique.py` não tinham nenhum antes da migração.
- **O Gemini tem piso de 10s**, declarado em `modelos.py`. Não é estimativa: com 8s a API responde `400 INVALID_ARGUMENT — "Manually set deadline 8s is too short. Minimum allowed deadline is 10s."` O 8s de `delegacao_ia/config.py` é legítimo para Groq/Cerebras/OpenAI e não deve mudar por causa disso; por isso o piso mora junto do provedor que o impõe, e o pedido é elevado até ele em vez de falhar.
- **`max_retries=0` no modelo, sempre.** Quantas vezes repetir é política de quem chama, e cada chamador já tem a sua, medida contra o próprio orçamento de tokens. Deixar o LangChain repetir por baixo multiplicaria essas contas em silêncio.
- **`PoliticaRepeticao` tem orçamentos separados por motivo de falha.** Não é preciosismo: o roteamento hierárquico já tinha descoberto na prática que um contador único faz um rate limit consumir as tentativas reservadas ao outro caso. O padrão é não repetir nada.
- **A chave de API nunca é lida aqui.** Chega pronta de quem chama, então cada pacote continua dono das próprias variáveis de `.env` e a tela de configurações continua mostrando cada uma na seção onde o usuário espera achá-la. Consequência: esta camada **não tem `config_schema()` e não entra em `PACOTES_COM_CONFIG`**, porque não lê `.env` nenhum.
- **A Cerebras usa `ChatOpenAI` com `base_url`**, não `langchain-cerebras`. O pacote dedicado exige Python <3.13 da versão 0.7.0 em diante, e esta venv é 3.13.4; a única versão instalável (0.6.0) arrasta um `langchain-openai <1` que **rebaixaria o pacote `openai` de 3.x para 2.x** e quebraria o cérebro Realtime, que é código em produção. A API da Cerebras é compatível com a da OpenAI (foi por isso que ela já cabia no helper genérico antes da migração), então é o mesmo caminho de rede de sempre.
- **`response_format` no estilo da OpenAI serve aos cinco provedores.** O `langchain-google-genai` 4.4 o traduz sozinho para `response_mime_type`/`response_json_schema` — confirmado lendo o código do pacote instalado, não suposto. É por isso que `agente.py` não tem nenhum `if provedor == "gemini"`; as esquisitices por provedor ficam em `modelos.argumentos_de_invocacao()`.
- **Modo JSON garante SINTAXE, nunca conteúdo.** Nenhum provedor promete que um nome de ferramenta citado lá dentro existe neste projeto. Quem pede JSON continua validando em código — ver `perfis/geracao.py`.

## Restrições a preservar

- **Nunca volte a abrir um cliente de LLM fora desta camada.** Código novo que precise consultar um modelo monta um `PedidoAgente`. Um `requests.post` ou um `genai.Client()` novo em qualquer pacote é uma regressão, não um atalho — a `grep -rn "genai.Client\|requests.post" jarvis/` só pode acertar `cerebro/gemini/cliente_live.py` (a sessão Live) e `identificacao_planta/plantnet_client.py` (não é LLM).
- **A classificação de erro de `erros.py` não pode ser afrouxada.** O 429 e o 400 de `"Tool choice is none, but model called a tool"` são os **únicos** casos que valem repetir, e o segundo é uma exceção justificada à regra de não repetir 4xx: medido, o mesmo pedido idêntico falha de 1 a 3 vezes em cada 6. Repetir um 401 é gastar o tempo do usuário para receber o mesmo erro.
- **A distinção dos DOIS 429 da Mistral depende de `RespostaAgente.cabecalho_do_erro()`.** Quando `x-ratelimit-limit-req-minute` vem zerado, a cota acabou e não vai reabrir sozinha; chamar isso de "limite por minuto" manda o usuário esperar por algo que não volta. `tipo_erro` sozinho não separa os dois casos — por isso a exceção original fica guardada na resposta.
- **`UsoTokens.bruto` não pode sumir.** `roteamento_hierarquico/medir_custo.py` mede cache hit por `usage.prompt_tokens_details.cached_tokens`, um campo que só existe no formato cru do provedor e que o `usage_metadata` padronizado do LangChain não carrega.
- **Isolamento de pacotes**: vários pacotes que agora importam esta camada são descritos no CLAUDE.md como autossuficientes "para serem copiados para outro projeto como estão". A mesma tensão já registrada na centralização dos prompts, resolvida do mesmo jeito — a padronização foi pedida explicitamente. Se um desses pacotes for extraído um dia, esta pasta vai junto.

## Testes

`testes/testar_voz_local.py`, blocos **6d** (repetição no limite de uso, preservação do motivo do erro, retry-after, ordem das mensagens) e **6j** (o 400 de ferramenta indevida, os orçamentos independentes, o plano B sem histórico). O ponto de mock desceu um nível com a migração: antes era `roteador.requests.post`, agora é `agentes.agente.modelos.criar_modelo` devolvendo um modelo falso cujo `invoke()` levanta exceções preparadas. O que está sendo verificado é o mesmo.
