---
name: sequencias-de-ferramentas
description: Guardrails para chamadas de ferramenta nos cérebros de voz do jarvis — sempre responder o call_id, limite de chamadas simultâneas, timeout por função, e por que nunca fazer retry automático. Use ao mexer em processar_chamada_de_funcao, ao registrar um pacote novo, ou ao investigar uma sequência de várias ferramentas que travou no meio.
---

# Sequências de chamadas de ferramenta

Esta skill cobre a camada de **orquestração**: o que acontece entre o modelo pedir
uma ferramenta e o resultado voltar. Para timeout de envio e supervisão de
tarefas, veja `resiliencia-sessao-voz`.

O contexto que torna tudo abaixo obrigatório: o jarvis declara **~50 ferramentas**
na sessão de voz. Quanto maior essa superfície, mais longas as sequências e maior
a chance de uma delas parar tudo.

## Regra 1 — todo `call_id` recebe resposta, sempre

Esta é a regra da qual todas as outras derivam. Nos protocolos de function calling
do Gemini Live e da OpenAI Realtime, **o modelo não pode voltar a falar enquanto
uma chamada estiver sem resposta**. Um `call_id` sem resposta não degrada a
conversa: ele a encerra, em silêncio, para sempre.

Consequências práticas, todas já implementadas:

- Recusar uma ferramenta é **responder recusando**, nunca ignorar. Ver
  `_recusar_chamada_de_funcao` (OpenAI) e `_responder_falha_para_lote` (Gemini).
- Timeout de função responde com texto de erro; não deixa o `call_id` aberto.
- Exceção dentro do despacho é capturada e vira resposta.
- Mutex visual ocupado devolve "tente de novo em instantes" — **não** fica
  esperando o mutex, o que seguraria o `call_id` por tempo indefinido.

Ao escrever qualquer caminho novo que possa sair de `processar_chamada_de_funcao`
mais cedo, a pergunta é uma só: *esse caminho responde o `call_id`?*

## Regra 2 — nunca responda o mesmo `call_id` duas vezes

Não existe forma testada de responder uma chamada já respondida. É por isso que a
resposta em duas fases do worker do Gemini, depois de mandar a resposta provisória
("estou trabalhando nisso"), entrega o resultado real por
`_enviar_anuncio_espontaneo` — e **não** por um segundo `send_tool_response`.

A armadilha estrutural que isso já causou: no worker do Gemini, o envio da
resposta precisou sair de dentro do `try` da FASE 1 para uma cláusula `else:`.
Dentro do `try`, um `TimeoutError` **do próprio envio** ficava indistinguível de
"a função ainda está rodando", e o código mandava a provisória e depois a FASE 2 —
respondendo o mesmo `call_id` duas vezes.

## Regra 3 — concorrência limitada, e o limite recusa respondendo

Cada chamada vira sua própria `asyncio.Task` (uma função lenta não pode bloquear o
laço de recepção, áudio incluído), rastreada em `self.tarefas_funcao_ativas`, com
teto de `LIMITE_TAREFAS_FUNCAO_SIMULTANEAS = 4` nos dois workers.

A checagem do limite é **síncrona**, uma comparação de tamanho de lista antes de
criar a task — nunca uma espera, que reintroduziria exatamente o bloqueio que a
concorrência existe para evitar. Acima do limite, a chamada é recusada com
resposta imediata; nunca enfileirada em silêncio.

## Regra 4 — timeout por função, dimensionado pela função

O padrão é 20s. Mas `executar_comando_admin` / `confirmar_comando_admin` têm
timeout próprio, bem maior (`TIMEOUT_COMANDO_LONGO_SEGUNDOS` + margem), porque o
padrão cortaria um comando longo **antes** do timeout interno dele, regredindo em
silêncio uma correção anterior.

Ao dar a um pacote um orçamento interno de vários minutos, some uma entrada em
`TIMEOUTS_FUNCAO_POR_NOME` / `TIMEOUTS_TAREFA_FUNCAO_POR_NOME`. Nunca deixe o
timeout externo menor ou igual ao interno.

## Regra 5 — nunca faça retry automático

Toda mensagem de falha devolvida ao modelo termina mandando **avisar o usuário e
não tentar de novo sozinho**. Uma ferramenta com efeito colateral (email, Discord,
comando administrativo, envio remoto) pode ter executado parcialmente antes de
falhar; repetir sozinho duplica o efeito.

Retry só existe em um lugar, e é explicitamente delimitado:
`roteamento_hierarquico/roteador.py` refaz um 429 e um 400 específico do Groq —
medidos, com orçamentos separados, e sem sleep no caso do 400.

## Regra 6 — o limite do cancelamento, que é do Python

Cancelar uma task que espera em `asyncio.to_thread(...)` para de **esperar** pela
thread, mas o Python não mata thread em execução. Uma função cujo trabalho
bloqueante genuinamente nunca volta continua ocupando um worker do pool pelo tempo
todo, mesmo depois de o usuário já ter sido avisado do timeout.

Um timeout externo garante que o **usuário** para de esperar. Nunca que o trabalho
parou. Onde isso importa de verdade, conserte na origem — foi o que
`stdin=subprocess.DEVNULL` fez pelo `admin_terminal`, depois de um `winget`
esperando input travar o app inteiro.

## Regra 7 — o mutex visual, e a diferença entre os dois padrões

Duas ferramentas podem disputar a webcam. Há dois padrões, e misturá-los quebra
um dos dois:

- **O cliente captura** (`identificar_planta`, `consultar_segunda_opiniao_visual`):
  o worker segura o mutex, captura, e injeta `imagem_bytes` em `args`.
- **O pacote captura sozinho** (`clicar_elemento_visual`): o nome entra em
  `TOOLS_QUE_CAPTURAM_SOZINHAS` e o mutex fica segurado durante o **despacho
  inteiro**.

Nunca chame `_mutex_funcao_visual()` de dentro de `processar_funcao_visual` ou de
algo que ela chama — o mutex já está retido e reportaria "ocupado" contra si mesmo.
