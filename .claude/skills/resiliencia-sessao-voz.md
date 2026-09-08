---
name: resiliencia-sessao-voz
description: Regras de resiliência para o transporte e a sessão dos três cérebros de voz do jarvis (Gemini Live, OpenAI Realtime, servidor local) — timeout em todo envio, supervisão de tarefas, watchdog de estado preso, e a regra do asyncio.to_thread. Use ao editar jarvis/cerebro/**, ao adicionar qualquer envio novo para uma sessão de voz, ou ao investigar uma chamada que "fica viva e muda".
---

# Resiliência da sessão de voz

Esta skill cobre a camada de **transporte e sessão**: o que impede uma chamada de
voz de congelar. Para limites e concorrência de *chamadas de ferramenta*, veja
`sequencias-de-ferramentas`. Para o método de investigar um travamento já
observado, veja `depurar-travamento-voz`.

O modo de falha que domina este projeto não é o crash — é o **congelamento
silencioso**: a chamada continua viva, o status na tela continua o mesmo, nenhuma
exceção sobe, e o usuário precisa matar o app pelo Gerenciador de Tarefas. Toda
regra abaixo existe porque esse modo de falha já aconteceu de verdade aqui.

## Regra 1 — nenhum envio para a sessão sem timeout

**Todo** envio passa por um wrapper com `asyncio.wait_for`. Nunca um `await` cru.

| Cérebro | Wrapper | Constante |
|---|---|---|
| Gemini Live | `_enviar_para_sessao` | `TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10` |
| OpenAI Realtime | `_enviar_para_sessao` | `TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10` |

Motivo, medido em bugs reais: uma conexão pode travar **sem erro e sem fechar**.
Um `await` cru nela nunca volta.

No worker da OpenAI o risco é pior, porque todo envio passa por `self.lock_envio`:
um envio pendurado **nunca devolve a trava**, e aí toda chamada de função seguinte
fica esperando para sempre para responder o próprio `function_call_output`. Como o
protocolo não deixa o modelo voltar a falar sem essa resposta, a conversa inteira
congela — e as tarefas centrais continuam vivas, então nada percebe.

O ponto do timeout não é só desistir do envio: **é soltar a trava.**

Ao adicionar um envio novo, o teste é mecânico:

```bash
grep -nE "await (self\.)?conexao\.(conversation|response|input_audio_buffer)" \
  jarvis/cerebro/openai_realtime/cliente_realtime.py
grep -n "await self.sessao.send_" jarvis/cerebro/gemini/cliente_live.py
```

Qualquer resultado é um envio cru = um congelamento esperando para acontecer.

## Regra 2 — quem detecta o travamento nunca tenta avisar por voz

Um aviso falado é **mais um envio**, pelo mesmo caminho que acabou de travar.
`monitorar_conexao` (Gemini) e o laço de supervisão de `executar()` (OpenAI)
apenas encerram a chamada e reportam por `erro_recebido` (a interface). Nunca
`_enviar_anuncio_espontaneo`.

## Regra 3 — toda tarefa de longa duração é supervisionada

`executar()` cria tarefas concorrentes e depois só as aguarda quando a chamada já
está terminando. Uma tarefa que morre no meio disso **morre sem ninguém ver**: a
chamada segue "conectada" e permanentemente quebrada.

- Gemini: `_tarefa_supervisionada("NOME", corrotina)` em cada uma das seis.
- OpenAI: o laço `asyncio.wait(tarefas, timeout=0.5, FIRST_COMPLETED)` checa
  `.exception()` a cada volta.

Nunca capture `asyncio.CancelledError` nesses supervisores — desde o 3.8 não é
subclasse de `Exception`, e o cancelamento normal do encerramento tem que passar
sem ser reportado como falha.

**Armadilha real:** `str(TimeoutError())` é **vazio**. Sempre
`str(erro) or type(erro).__name__`, ou a mensagem na interface termina em
dois-pontos e nada. Já foi corrigido duas vezes neste projeto.

## Regra 4 — guarde a referência de toda `asyncio.Task`

O asyncio mantém referência **fraca** a uma task em execução. Uma task criada e
esquecida pode ser coletada pelo garbage collector no meio do caminho.

```python
# ERRADO — a task pode sumir
asyncio.create_task(self.processar_chamada_de_funcao(...))

# CERTO
tarefa = asyncio.create_task(corrotina, name=f"FUNÇÃO:{nome}")
self.tarefas_funcao_ativas.append(tarefa)
tarefa.add_done_callback(self._ao_finalizar_tarefa_funcao)
```

O `name=` não é enfeite: é o que deixa o watchdog dizer *qual* tarefa morreu.

## Regra 5 — nada que bloqueia roda no event loop

Toda chamada síncrona vai por `asyncio.to_thread(...)`. Violar isso já causou o
bug "responde, executa a ação, e depois demora muito para voltar a me ouvir":
`capturar_camera_bytes()` leva **2,8s** medidos nesta máquina e estava sendo
chamada direto no loop em 7 lugares, congelando microfone e reprodução junto.

Exceção deliberada: a escrita no dispositivo de áudio usa um
`ThreadPoolExecutor(max_workers=1)` **dedicado**, nunca `asyncio.to_thread`. O
pool padrão é compartilhado com as outras ~36 chamadas bloqueantes do arquivo, e
com ele cheio um bloco de áudio esperou **1,69s** — cerca de 40 blocos de fala, o
que o usuário percebe como travar no meio da frase com a CPU ociosa.

## Regra 6 — o watchdog só vigia o impossível, nunca o ocioso

`vigiar_travamento` (Gemini) checa estados que **não podem** existir em operação
normal: `alfred_falando` preso além de 60s, mutex visual preso além de 120s, fila
de saída parada, tarefa morta, microfone sem entregar bloco há 10s. Onde é seguro,
ele **destrava** em vez de só reclamar.

Nunca adicione uma checagem do tipo "faz tempo que não acontece nada" — silêncio é
o estado normal de uma chamada, e isso transformaria o watchdog em gerador de
alarme falso. Toda checagem nova precisa da mesma propriedade, mais um guard de
"avisa uma vez por episódio" se a condição persiste entre ticks.

## Regra 7 — falhar não pode custar a chamada, exceto no transporte

Erro de ferramenta, timeout de função, falha de roteamento: reporta por
`erro_recebido` e **volta a escutar**. Só falha de conexão, de microfone ou de
tarefa central encerra a chamada.

E nunca engula o erro em silêncio: uma função que falhou devolve um texto que
manda o modelo **avisar o usuário e não tentar de novo sozinho** — retry
automático numa ação com efeito colateral (email, comando admin, mensagem) é pior
que a falha.
