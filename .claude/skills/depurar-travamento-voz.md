---
name: depurar-travamento-voz
description: Método para investigar travamento, congelamento ou comportamento intermitente numa chamada de voz do jarvis — reproduzir em harness offline com sessão falsa, isolar a causa raiz antes de corrigir, e provar que sumiu. Use quando o relato for "travou no meio", "parou de responder", "ficou mudo", "tive que reiniciar" ou qualquer bug que só acontece às vezes.
---

# Depurar um travamento de chamada de voz

Correção sem reprodução é chute. Este projeto já pagou por isso: uma investigação
de congelamento chegou a ser aberta e pausada **com zero dados coletados**, e a
causa real (uma captura de câmera de 2,8s bloqueando o event loop) só apareceu
quando alguém mediu em vez de supor.

## 1. Extraia o formato do relato antes de abrir código

O relato do usuário já elimina metade das hipóteses. As perguntas que discriminam:

| Pergunta | O que a resposta descarta |
|---|---|
| Respondeu e **depois** parou, ou nunca respondeu? | "Depois" inocenta a conexão inicial e a ferramenta que rodou |
| **Apareceu erro na interface?** | Se não: não houve exceção — `_tarefa_supervisionada` teria emitido |
| Status parado em qual texto? | Aponta o último ponto que executou |
| Ficou mudo ou ficou surdo? | Mudo = reprodução/envio · surdo = microfone/recepção |
| O app fechava, ou precisou do Gerenciador de Tarefas? | Gerenciador = thread bloqueada, não exceção |
| Aconteceu depois de qual correção já instalada? | Descarta tudo que aquela correção cobre |

**"Sem erro na interface" é o dado mais valioso do conjunto.** Ele elimina de uma
vez toda hipótese que envolva uma exceção, porque os supervisores emitem
`erro_recebido` em qualquer `Exception`. Sobra: espera que nunca volta, thread
bloqueada, ou flag preso.

## 2. Reproduza OFFLINE, nunca numa chamada ao vivo

Esta é a regra específica deste projeto. Uma chamada ao vivo depende de rede,
quota, microfone, timing do servidor e do humor do modelo — e o que se investiga
aqui é concorrência, que exige controle exato do tempo.

O padrão que este projeto já usa em 271 verificações: um worker **real**, com uma
sessão **falsa** cujos envios você controla.

```python
class EnvioFalso:
    async def __call__(self, **kwargs):
        self.dono.enviados.append((self.rotulo, kwargs))
        if self.dono.pendurar:
            await asyncio.Event().wait()   # nunca resolve
```

Isso reproduz a conexão travada em 1 segundo, de forma determinística, sem
internet. Encurte a constante de timeout durante o teste
(`cliente_realtime.TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 1`) e restaure num `finally`.

Referência viva: `testes/testar_openai_realtime_travamento.py`.

Onde o objeto real for insubstituível (só a rede responde a pergunta), mantenha o
teste offline **e** faça uma medição isolada à parte — como o cronômetro direto em
`capturar_camera_bytes()` que produziu os 2,8s.

## 3. Hipóteses, em ordem de probabilidade neste projeto

Vá nesta ordem; as três primeiras cobrem quase tudo que já aconteceu aqui:

1. **`await` sem timeout** — envio para a sessão, escrita no dispositivo de áudio,
   espera por arquivo. Procure `await` cru em qualquer coisa de I/O.
2. **Trava retida** — um `async with lock` cujo corpo pode pendurar. Pergunte
   sempre: *se isto pendurar, quem mais fica esperando?*
3. **Chamada bloqueante no event loop** — falta de `asyncio.to_thread`. Meça a
   função com um cronômetro; não confie na intuição sobre o que é "rápido".
4. **Task perdida** — `create_task` sem referência guardada (coleta pelo GC), ou
   sem supervisão (exceção não observada).
5. **Flag preso** — booleano que gateia o microfone e não voltou a False.
6. **Acústico, não código** — barge-in com o áudio saindo por caixa de som. Se
   o contador de `[INTERRUPÇÃO]` sobe enquanto o usuário está calado, a correção é
   `config.json` → `"interrupcao": false`, não código.

## 4. Prove a causa antes de corrigir; prove a correção depois

Duas provas separadas, ambas obrigatórias:

- **Causa:** o teste falha *antes* da correção, pelo motivo previsto. Um teste que
  já passa antes não provou nada sobre o bug.
- **Correção:** o mesmo teste passa depois, e a suíte existente continua verde.

Quando não der para provar a causa raiz — acontece com intermitente raro —, diga
isso explicitamente em vez de apresentar a hipótese como fato. Reforço de defesa
sem confirmação é legítimo; **chamá-lo de correção confirmada não é.**

## 5. Não conserte dois problemas de uma vez

Cada travamento vira uma correção isolada e testável. Este projeto tem histórico
de investigações onde a segunda correção mascarou se a primeira funcionou. Se
achar um segundo defeito real no caminho, registre e trate separado.

## 6. Registre o que ficou sabido

Depois de resolver, atualize o `docs/*.md` da área com **o bug real, o sintoma
relatado e a medição** — não só a regra. É a diferença entre "envolva os envios em
timeout" e "envolva os envios em timeout porque sem isso a trava fica retida e a
conversa congela, relatado como 'travou no meio de uma sequência de ferramentas'".
A segunda forma é a que impede alguém de reverter a correção seis meses depois.
