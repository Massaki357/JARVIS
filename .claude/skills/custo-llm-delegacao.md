---
name: custo-llm-delegacao
description: Política atual de quando o Jarvis deve delegar uma tarefa de texto para Groq, Cerebras ou OpenAI via delegacao_ia.delegar_tarefa — e quando deve responder sozinho, sem delegar nada.
---

# Política de custo: Groq / Cerebras / OpenAI

Este documento reflete o estado **atual** do roteador em `jarvis/pacotes/delegacao_ia/roteador.py` e
da seção `# DELEGAÇÃO DE TAREFAS` do `instrucao_sistema` em
`jarvis/gemini/cliente_live.py`. Releia esses dois arquivos antes de usar esta skill como
referência — a política já mudou uma vez neste projeto (havia um terceiro tipo,
`raciocinio_complexo`→OpenAI, removido) e pode mudar de novo.

## Os três tipos de `tipo_tarefa`

| `tipo_tarefa` | Provedor principal | Fallback | Uso |
|---|---|---|---|
| `pergunta_rapida` | Groq | Cerebras | Livre — fatos objetivos, cálculo simples, definição curta |
| `resumo` | Cerebras | Groq | Livre — resumir texto/conteúdo longo já fornecido |
| `segunda_opiniao` | OpenAI | **nenhum** | Raro — só decisão de peso real/dinheiro/risco significativo |

`pergunta_rapida` e `resumo` passam pelo caminho genérico
(`MAPA_PROVEDOR_PRINCIPAL`/`MAPA_PROVEDOR_FALLBACK`): se o principal falhar, tenta o
outro provedor barato/rápido; se os dois falharem, retorna `MENSAGEM_INDISPONIVEL` — o
Jarvis responde sozinho, **sem mencionar a falha ao usuário**.

`segunda_opiniao` é tratado à parte, de propósito, por dois motivos que não podem ser
"otimizados" sem quebrar a intenção da feature:

1. **Sem fallback para Groq/Cerebras.** Cair pra um provedor que o Jarvis já usa
   rotineiramente descaracterizaria a ideia de "segunda opinião independente".
2. **Mensagem de falha diferente** (`MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL`), que
   instrui o Jarvis a **avisar o usuário** que não conseguiu confirmar a resposta com
   uma segunda IA desta vez — o oposto do comportamento silencioso dos outros dois
   tipos, porque aqui a ausência da segunda opinião é informação relevante pra uma
   decisão de peso.

Quando `segunda_opiniao` tem sucesso, a resposta da OpenAI não é repassada crua — vem
embrulhada com uma instrução pro Jarvis comparar com o próprio raciocínio e sintetizar
os dois pontos de vista (onde concordam, onde divergem, qual conclusão parece mais
sólida).

## Por que essa assimetria existe

OpenAI é o provedor mais caro dos três em uso. Groq e Cerebras são
rápidos/baratos/suficientes pra maioria dos raciocínios — inclusive o próprio Gemini,
que já está conduzindo a conversa, dá conta de planejamento/comparação/análise sem
precisar delegar nada. `segunda_opiniao` existe só para o caso em que **uma perspectiva
de IA independente muda de fato a qualidade da resposta** — tipicamente decisões
financeiras, ou qualquer coisa de risco/consequência real onde vale o custo de uma
segunda IA conferindo.

## Exemplos usados para treinar a distinção (na `instrucao_sistema`)

**Usam `segunda_opiniao`** (decisão de peso/dinheiro/risco real):
- "pesquise quais as melhores ações para eu comprar agora"
- "vale a pena eu pedir demissão pra abrir esse negócio"
- "analise esse contrato antes de eu assinar"

**Não usam `segunda_opiniao` nem delegação nenhuma** — o Jarvis responde direto:
- "explique como funciona juros compostos" (conhecimento direto, não é uma decisão)
- "compare React e Vue" (comparação técnica, sem risco real)
- "me ajuda a planejar minha semana" (planejamento comum)

Regra geral pra qualquer tarefa de raciocínio nova que não se encaixe claramente nos
exemplos acima: se não envolve risco real ou decisão de peso, o Jarvis responde com o
próprio raciocínio — não delega nada, nem pra Groq/Cerebras nem pra OpenAI.

## O que NÃO fazer ao mexer nisso

- Não adicione um segundo caminho de código que chame a OpenAI diretamente (em
  `cliente_live.py`, num pacote novo, etc.) — `delegar_tarefa(tipo_tarefa=
  "segunda_opiniao", ...)` é o único ponto de acesso à OpenAI no projeto (ver
  `CLAUDE.md`, seção "Key constraints").
- Não dê fallback pra `segunda_opiniao` sem entender que isso muda o propósito da
  feature (deixaria de ser uma opinião "independente").
- Não silencie a falha de `segunda_opiniao` — isso é deliberadamente diferente do
  comportamento de `pergunta_rapida`/`resumo`.
- Não reintroduza `raciocinio_complexo`→OpenAI (ou equivalente) sem uma decisão
  explícita do usuário — foi removido de propósito porque Gemini/Groq já cobrem esse
  caso sem custo extra.
- Se um modelo hardcoded em `jarvis/pacotes/delegacao_ia/config.py` (`MODELO_GROQ`/`MODELO_CEREBRAS`/
  `MODELO_OPENAI`) começar a falhar com erro tipo `model_not_found`, o catálogo do
  provedor provavelmente mudou — confirme o nome novo consultando `/v1/models` do
  provedor ao vivo, não adivinhe a partir de conhecimento geral (os nomes da família
  Llama já ficaram obsoletos uma vez nesse projeto).
