# jarvis/pacotes/agente_ferramentas/ — o sub-agente de ferramentas (Groq)

> Contexto detalhado deste módulo. Leia antes de editar arquivos desta área.

## Por que ele existe: o prefixo de 18 mil tokens

Medido neste projeto, toda chamada abria com **18.182 tokens de prefixo** — 10.623 de schema de ferramenta e 7.559 de instrução de sistema — e um cérebro de voz caro paga isso em **todo turno**, inclusive no turno em que o usuário só disse "bom dia".

A maior parte era manual de ferramenta que não seria usada. Então a maioria das ferramentas **deixou de ser declarada**: o cérebro descobre a certa com `buscar_ferramenta` e a executa com `executar_ferramenta`.

Medido com o tokenizador real, perfil `completo`:

| | original | 1ª etapa (sub-agente) | 2ª etapa (lista direta) |
|---|---:|---:|---:|
| schemas de ferramenta | 10.623 | 5.135 | **2.950** |
| instrução de sistema | 7.559 | 4.079 | **816** |
| **prefixo por turno — Gemini Live** | **18.182** | **9.214** | **3.766** |
| **prefixo por turno — OpenAI Realtime** | — | — | **2.091** |
| ferramentas declaradas (Gemini) | 64 | 25 | 26 |
| ferramentas *habilitadas* | 64 | 64 | **64** |

**−79% por turno em relação ao original, sem perder nenhuma capacidade.** O que saiu do prefixo passou a ser pago só quando usado — ver "Custo sob demanda" abaixo.

## O fluxo, na ordem

1. **A função está na lista do cérebro?** A lista são as próprias funções declaradas, cada uma com uma descrição de uma linha. Se estiver, ele chama `ler_instrucao_ferramenta(nome)` **uma vez por conversa** e depois usa a função direto. `encerrar_chamada` e `pausar_chamada` dispensam a leitura.
2. **Não está?** Ele chama `buscar_ferramenta(pedido)` — o sub-agente na Groq, que só enxerga as ferramentas **ocultas** — e depois `executar_ferramenta(nome, argumentos)`.

A ordem é essa (lista primeiro) porque consultar a lista é de graça — ela já está no prefixo —, enquanto o sub-agente é uma ida e volta. "Olha minha tela" custa duas idas e voltas; na ordem inversa custaria três, e a resposta "nenhuma" do sub-agente ficaria no histórico.

## O sub-agente

O cérebro descreve o que o usuário quer; o sub-agente diz **qual ferramenta oculta atende e exatamente como executá-la**.

```
cérebro  ──buscar_ferramenta("o usuário pediu para verificar a tela dele")──▶  este pacote
                                                                                    │
                                                              sub-agente na Groq lê o catálogo
                                                                    (nome + descrição)
                                                                                    │
cérebro  ◀── "FERRAMENTA RECOMENDADA: descrever_tela / O QUE FAZ: ... / ──────────┘
              COMO CHAMAR — parâmetros: - pergunta (texto, opcional): ..."
```

*(O diagrama acima é da primeira etapa: hoje `descrever_tela` é uma ferramenta direta e nem aparece no catálogo do sub-agente. O mecanismo é o mesmo para as ocultas, que o cérebro então roda com `executar_ferramenta`.)*

## Arquivos

| arquivo | papel |
|---|---|
| `__init__.py` | o contrato do projeto, expondo `ler_instrucao_ferramenta(nome)`, `buscar_ferramenta(pedido)` e `executar_ferramenta(nome, argumentos)` |
| `executor.py` | roda uma ferramenta que o cérebro não tem declarada, e **recusa** as que ele tem |
| `manual.py` | entrega, sob demanda, as regras de uso: a seção do `manual_ferramentas.md` (ocultas) ou a instrução da ferramenta direta |
| `catalogo.py` | monta a lista **nome + descrição + parâmetros**, derivada das `FunctionDeclaration` reais |
| `subagente.py` | a consulta à Groq pela camada de agentes, com resposta em JSON e validação dos nomes |
| `instrucoes.py` | transforma a escolha no texto que o cérebro lê ("como chamar", parâmetro a parâmetro) |
| `config.py` | `.env` deste pacote + `config_schema()` |

O prompt do sub-agente é `jarvis/nucleo/prompts/geral/agente_ferramentas_busca.md` (constante `prompts.AGENTE_FERRAMENTAS_BUSCA`) — `geral/` porque o sub-agente responde igual para qualquer cérebro ativo.

## Declarada vs. habilitada

São duas coisas diferentes desde esta mudança, e confundi-las é o erro mais fácil de cometer aqui:

- **habilitada** — o perfil permite usar. Não mudou nada; continuam 64.
- **declarada** — vai no `tools` da sessão e é paga em todo turno. Agora são 25.

Quem separa as duas é `perfis.preparar_chamada()` → `_sem_as_ocultas()`, o **único** ponto por onde os dois workers resolvem a lista. Foi isso que permitiu fazer toda a economia **sem editar `cliente_live.py` nem `cliente_realtime.py`**.

O conjunto oculto é **derivado** em `registro_pacotes.ferramentas_ocultas()`:

```
ocultas = ferramentas de pacote
        − TOOLS_QUE_PRECISAM_DE_IMAGEM
        − TOOLS_SILENCIOSAS
        − TOOLS_QUE_CAPTURAM_SOZINHAS
        − FERRAMENTAS_SEMPRE_DECLARADAS
```

Um pacote novo nasce barato sozinho; um pacote novo que precise de imagem, mutex ou silêncio entra na lista certa lá em cima e é poupado daqui automaticamente.

### O que NUNCA pode ser ocultado

1. **As 16 nativas.** Não são despachadas por pacote nenhum — vivem dentro do worker e dependem da sessão viva.
2. **As 7 especiais.** Os dois workers decidem **pelo nome da função que o modelo chamou** se capturam a imagem, se seguram o mutex visual e se descartam o áudio do turno. Chamadas via `executar_ferramenta`, o nome que chega ao worker é `"executar_ferramenta"` e os três comportamentos **sumiriam em silêncio** — exatamente o bug já documentado em `TOOLS_QUE_PRECISAM_DE_IMAGEM` (pedir para olhar a tela e ouvir que deu erro na câmera). `executor.py` recusa essas por nome, como rede de segurança.
3. **As duas tools deste pacote.** Esconder a porta de entrada atrás dela mesma tranca o cérebro do lado de fora.

## O manual sob demanda

16 seções do `sistema.md` (`## CRIAR ARQUIVO`, `## AGENDA`, `## DISCORD`…) moveram para `dados/perfis/<slug>/manual_ferramentas.md` — 3.836 tokens que eram pagos em todo turno e agora chegam junto com a ferramenta recomendada. **O texto é o mesmo, palavra por palavra.**

O mapa ferramenta → seção é **derivado**: cada seção já cita pelo nome as ferramentas de que trata. Uma seção que deixe de citar um nome simplesmente não é entregue — falha silenciosa e inofensiva, ao contrário de um mapa desatualizado apontando para a seção errada.

**O que deliberadamente NÃO moveu:** as seções que mencionam alguma ferramenta que **continua declarada** (EMAIL, ENVIO DE CAPTURA, VISÃO, VÍDEO AO VIVO, IDENTIFICAÇÃO VISUAL, MOUSE, CLIQUE, ESCRITA). Elas são mistas, e recortá-las na unha significaria reescrever prosa que carrega trava de segurança ("nunca invente destinatário", "só quando o usuário pedir explicitamente"). Deixar ~4 mil tokens na mesa é barato perto de perder uma dessas frases sem perceber.

## A lista de ferramentas diretas

`dados/perfis/<slug>/ferramentas_diretas/`, lida por `jarvis/nucleo/perfis/ferramentas_diretas.py`:

- **`lista_ferramentas_diretas.md`** — uma linha por ferramenta declarada: `nome: o que faz — quando pode ser usada`. **Ela vira a descrição do schema.** No começo de toda chamada, `perfis.filtrar_declaracoes` troca a descrição longa de cada ferramenta pela linha dela. Não existe um bloco de "lista" separado no prompt: o cérebro vê nome + linha curta nas próprias funções, e não paga a mesma informação duas vezes.
- **A parte depois do travessão é a TRAVA** — a regra que precisa estar visível na hora de *decidir* ("só se o usuário pedir", "nunca inventado"). É por ela que a restrição de visão e email continua diante do modelo mesmo com o manual fora do prompt; o `sistema.md` ainda repete essa restrição em duas linhas, na seção de segurança.
- **`<nome>.md`** — as instruções completas de uma ferramenta, lidas com `ler_instrucao_ferramenta`. O que chega ao cérebro é a **descrição longa original do schema** (guardada no momento da troca — inclusive das nativas do Gemini, inalcançáveis de outro jeito) seguida do arquivo. `descrever_tela.md` e `descrever_camera.md` estão vazios de propósito: as regras delas já estavam inteiras na descrição original, e escrever uma regra ali seria inventá-la.

**Nenhuma regra se perdeu na divisão**: as 89 frases das dez seções que saíram do `sistema.md` foram conferidas uma a uma contra o destino (prompt novo, arquivos diretos e manual das ocultas). Duas dessas seções tinham regras de ferramentas **ocultas** misturadas (`abrir_camera`/`fechar_camera`, `clicar_mouse`/`duplo_clique_mouse`/`clique_direito_mouse`) — elas foram para o `manual_ferramentas.md`, senão o sub-agente deixaria de entregá-las.

**O que ficou no `sistema.md`**: identidade, personalidade, preferências, estilo, segurança (com as travas gerais de visão e email), "FIM DO ATENDIMENTO" (perguntar se precisa de mais algo e pausar — comportamento de conversa, não instrução de ferramenta), o fluxo "SUAS FERRAMENTAS" e o retorno das funções.

### Custo sob demanda

Tudo que o cérebro lê **fica no histórico da chamada** e é repago nos turnos seguintes — por isso cada instrução é lida uma vez por conversa, e os cabeçalhos das respostas são mínimos. Tamanhos medidos:

| `ler_instrucao_ferramenta(...)` | tokens |
|---|---:|
| `descrever_tela` | 76 |
| `rolar_pagina` | 148 |
| `analisar_tela` | 169 |
| `pausar_chamada` | 221 |
| `salvar_print_tela` | 254 |
| `preparar_email` | 638 |
| `enviar_captura_email` | 807 |

As quatro `enviar_captura_*` repetem o mesmo bloco sobre `capturar_novo`/`tipo_captura`, de propósito: o cérebro lê um arquivo só, e cada um precisa estar completo sozinho.

## Arquitetura e decisões de design

- **O catálogo não é uma lista nova.** Tudo é derivado: quais ferramentas existem e o resumo de uma linha vêm de `perfis/catalogo_ferramentas.catalogo_completo()`; a descrição completa e os parâmetros vêm da própria `types.FunctionDeclaration` que o pacote já expõe — a mesma que o cérebro recebe. Um pacote novo aparece aqui sozinho, com a descrição certa, assim que entra em `PACOTES_REGISTRADOS`. Escrever uma quarta lista à mão seria garantir que uma delas envelhecesse em silêncio.
- **`buscar_ferramenta` nunca executa nada, só devolve texto.** Quem executa é `executar_ferramenta`, numa chamada separada do cérebro. Manter as duas separadas é o que preserva o modelo mental do projeto: o cérebro continua sendo quem decide agir, e cada ação continua sendo uma tool call dele.
- **`argumentos` é uma STRING JSON, não um objeto.** Os dois provedores lidam mal com um parâmetro de esquema aberto (`object` sem `properties`), e string funciona igual nos dois. JSON inválido vira dicionário vazio e a própria ferramenta responde qual parâmetro faltou — mensagem muito melhor que "JSON malformado".
- **O catálogo do sub-agente tem só as ferramentas OCULTAS.** O cérebro consulta a própria lista antes de chamá-lo, então oferecer as diretas de novo seria cobrar duas vezes pela mesma busca e engordar o prompt da Groq. A única exceção é quando não existe nenhuma oculta (`FERRAMENTAS_SOB_DEMANDA=false`): aí o catálogo inteiro vale, senão `buscar_ferramenta` ficaria sem resposta possível. Como rede de segurança, a resposta "nenhuma ferramenta serve" lembra o cérebro de conferir a própria lista — cobre o caso de ele pular a ordem e perguntar ao sub-agente por algo que era direto.
- **O catálogo é filtrado pelo perfil ativo E pelo cérebro em uso** (`perfis.ferramentas_efetivas()` ∩ `catalogo_ferramentas.nomes_do_cerebro()`). Recomendar algo que o perfil desligou, ou uma nativa do Gemini para o OpenAI Realtime (que tem 4 nativas contra 16), seria mandar o cérebro chamar o que ele não tem. Se a resolução falhar, **não filtra nada** — um catálogo grande demais é muito melhor que um vazio, que deixaria o sub-agente sem resposta possível.
- **As três tools deste pacote nunca entram no próprio catálogo.** Um sub-agente que pode recomendar a si mesmo manda o cérebro consultá-lo de novo, e o turno vira laço.
- **As descrições das três tools deste pacote são curtas de propósito.** Elas estão sempre declaradas, então são pagas em todo turno; o fluxo completo é explicado **uma vez**, na seção "SUAS FERRAMENTAS" do `sistema.md`.
- **`ler_instrucao_ferramenta` nunca diz "pode usar" para um nome que não existe** — responde que a função não existe e aponta `buscar_ferramenta`. O nome vem do modelo, e também nunca vira caminho de arquivo sem passar por um `fullmatch` de nome de ferramenta (`../sistema` não lê nada).
- **Modo JSON com esquema** (`esquema_resposta` da camada de agentes), confirmado ao vivo no `openai/gpt-oss-20b` — isso resolveu a dúvida que estava registrada como "não confirmada" no comentário de `ROTEAMENTO_ETAPA1_INSTRUCAO`. Mesmo assim **todo nome que volta é conferido contra o catálogo real**: modo JSON garante sintaxe, nunca conteúdo. Nome inventado é descartado com um aviso no console, nunca repassado.
- **Três respostas possíveis, e as três são explícitas**: recomendação, "nenhuma ferramenta serve" (resultado legítimo — o cérebro responde sozinho) e "não consegui consultar" (falha). As duas últimas **não podem ser confundidas**: o texto de falha manda explicitamente NÃO fingir que a ação aconteceu. Este projeto já pagou por essa confusão — uma falha de roteamento tratada como conversa fez o assistente dizer que estava abrindo o navegador enquanto nada abria (ver `ResultadoTurno.falhou` em `roteamento_hierarquico/roteador.py`).
- **O resultado nunca é falado.** É um manual de parâmetros. O texto termina lembrando disso, a descrição da tool repete, e `sistema.md` do perfil padrão abre uma exceção explícita na seção "RETORNO DAS FUNÇÕES" (que manda narrar o resultado de toda função).

## Não confundir com `jarvis/roteamento_hierarquico/`

|  | `roteamento_hierarquico` | `agente_ferramentas` |
|---|---|---|
| quem chama | o cérebro de voz **local**, que não tem tool calling nativo | o **cérebro**, no meio do próprio raciocínio |
| o que faz | escolhe a ferramenta **e executa** | devolve **informação**, não ação |
| substitui | o raciocínio do cérebro | nada — complementa |

Os dois leem catálogos derivados das mesmas `FunctionDeclaration`; nenhum dos dois tem lista própria. Por isso `buscar_ferramenta` está em `CATALOGO_CURTO` (para a tela de perfis ter um resumo dela e `verificar_catalogo_atualizado()` ficar em dia) mas em `FERRAMENTAS_FORA_DO_ROTEAMENTO` — oferecê-la à etapa 1 seria gastar uma chamada de LLM para descobrir que se deve gastar outra com a mesma pergunta.

## Variáveis de .env

Nenhuma obrigatória. `GROQ_API_KEY` é reaproveitada (já existe para `delegacao_ia` e o roteamento hierárquico) e **por isso não aparece no `config_schema()` deste pacote** — dois campos sensíveis mostrando a mesma chave seria confuso.

```
AGENTE_FERRAMENTAS_MODELO=<padrão openai/gpt-oss-20b>
AGENTE_FERRAMENTAS_CATALOGO_COMPLETO=<true/false, padrão false>
FERRAMENTAS_SOB_DEMANDA=<true/false, padrão true — lida por jarvis/nucleo/config.py>
```

`FERRAMENTAS_SOB_DEMANDA=false` volta a declarar **todas** as ferramentas, **com as descrições longas** (a troca pela lista curta também é desligada). As regras de uso continuam sob demanda por `ler_instrucao_ferramenta`, que nesse modo responde por qualquer ferramenta — direta ou não. É a saída se o modelo começar a se comportar pior sem ver as descrições — o risco real desta troca é ele deixar de perceber que **pode** fazer algo, não executar algo errado. Por isso a seção `## SUAS FERRAMENTAS` do `sistema.md` lista as categorias do que existe fora da lista e diz, em maiúsculas, para nunca responder "não consigo" sem antes chamar `buscar_ferramenta`.

`AGENTE_FERRAMENTAS_CATALOGO_COMPLETO=true` troca o resumo de uma linha pela descrição completa de cada ferramenta no catálogo de busca. Escolhe melhor entre ferramentas parecidas e **custa muito mais**: o catálogo padrão mede ~1,6 mil tokens (cabe no teto de 8 mil tokens/minuto do tier gratuito da Groq, medido neste projeto); o completo passa de 10 mil e estoura o tier numa única chamada. Só ligue com plano pago ou modelo local. Em qualquer um dos casos, a ferramenta **recomendada** volta com a descrição completa e todos os parâmetros — a variável decide só o que vai no catálogo de busca.

## Restrições a preservar

- **Nenhum import de `jarvis.nucleo.registro_pacotes` no topo de um arquivo deste pacote.** Ele está DENTRO de `PACOTES_REGISTRADOS`: importar o registro em tempo de módulo fecha o ciclo e o app não sobe. Todos os imports de `catalogo.py` são adiados para dentro das funções, de propósito.
- **Todo nome devolvido pelo modelo passa por `catalogo.procurar()` antes de chegar ao cérebro.** Não afrouxe isso para "corrigir" grafia ou aproximar nomes parecidos: recomendar uma ferramenta errada com confiança é pior do que admitir que não achou.
- **O texto de falha não pode virar o de "nenhuma ferramenta serve".** São opostos, e a diferença é o que impede o assistente de narrar uma ação que nunca aconteceu.
- **O catálogo é remontado a cada chamada, nunca cacheado no módulo.** O perfil ativo e o cérebro em uso mudam entre chamadas; um catálogo cacheado recomendaria ferramentas de um cenário que não vale mais. São dois dicionários em memória, não rede.

## Ressalva conhecida

O filtro lê o **perfil ativo agora**, e trocar de perfil só vale a partir da próxima chamada. Se o usuário trocar no meio de uma chamada, o filtro passa a usar o perfil novo enquanto o cérebro ainda roda com o antigo. A consequência é recomendar uma ferramenta que o cérebro não encontra — o mesmo resultado de não filtrar nada, que já é o comportamento de fallback.

## Restrições adicionais depois da economia

- **Nunca mova uma ferramenta de `TOOLS_QUE_PRECISAM_DE_IMAGEM`, `TOOLS_SILENCIOSAS` ou `TOOLS_QUE_CAPTURAM_SOZINHAS` para o conjunto oculto.** Os workers as reconhecem pelo nome da tool call; por `executar_ferramenta` esse nome não chega, e a falha é silenciosa.
- **`_sem_as_ocultas()` nunca pode levantar exceção.** Se a derivação falhar, ela devolve a lista intacta e a chamada abre com tudo declarado — caro, mas funcionando. Falhar caro é melhor que falhar mudo.
- **Cada seção do `manual_ferramentas.md` precisa citar pelo nome as ferramentas de que trata**, ou deixa de ser entregue.
- **`filtrar_declaracoes` devolve CÓPIAS com a descrição trocada, nunca altera a declaração recebida.** As declarações de pacote são objetos de módulo compartilhados com o catálogo do sub-agente; mudar no lugar substituiria para sempre a "descrição completa" que ele lê.
- **A lista é carregada em `preparar_chamada`, não em `filtrar_declaracoes`.** Os dois workers chamam `filtrar_declaracoes` dentro do laço de asyncio; `preparar_chamada` roda em `asyncio.to_thread` logo antes. Ler o disco no filtro bloquearia o laço de eventos da chamada.
- **Toda ferramenta direta precisa de uma linha na lista E de um `<nome>.md`.** Sem a linha, ela só volta a pagar a descrição longa (mais caro, nunca quebrado). Sem o arquivo, `ler_instrucao_ferramenta` devolve só a descrição original.
- **Uma regra de ferramenta nova nunca vai para o `sistema.md`.** Oculta → seção no `manual_ferramentas.md` citando o nome; direta → linha na lista + `ferramentas_diretas/<nome>.md`.
- **Perfis sem essas pastas caem nas do `completo`.** Um perfil criado pela tela de perfis nasce só com `perfil.json` e `sistema.md`; tirar esse fallback faria as regras sumirem ao trocar de perfil.
