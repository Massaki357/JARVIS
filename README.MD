Crie um arquivo .env e coloque as seguintes API KEYs:

```
GEMINI_API_KEY=

OPENAI_API_KEY=

MISTRAL_API_KEY=

GROQ_API_KEY=

CEREBRAS_API_KEY=
```

Acesse o site:
```
myaccount.google.com/apppasswords
```
Conecte a conta do gmail que você quer que o jarvis acesse e gere a senha de APP

Para o ALFRED conseguir enviar e ler emails, adicione também no .env:
```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_REMETENTE=seu-email@gmail.com
EMAIL_SENHA_APP=sua-senha-de-app (não é a senha normal da conta)
```

EMAIL_SMTP_* é usado para enviar email e EMAIL_IMAP_* para ler a caixa de entrada, mas EMAIL_REMETENTE e EMAIL_SENHA_APP são os mesmos para as duas coisas.

-------------------------------------------------

Para o ALFRED conseguir mandar comando pra outras máquinas (rede_jarvis, via MQTT),
adicione também no .env:
```
MQTT_HOST=
MQTT_PORT=8883
MQTT_USERNAME=
MQTT_PASSWORD=
TOKEN_REDE_JARVIS=
NOME_MAQUINA=
PASTA_TRANSFERENCIAS_PADRAO=
GOOGLE_SERVICE_ACCOUNT_JSON=
PEDIR_PERMISSAO=true
```

Antes disso, o projeto tentou Telegram duas vezes (bot único e depois um bot por
máquina) e nenhuma funcionou por restrições da própria plataforma — bots nunca recebem
de volta as próprias mensagens, nem mensagens de outros bots. MQTT é feito exatamente
pra esse tipo de comunicação máquina-a-máquina e não tem esse problema: qualquer
máquina publica em um tópico e todas as inscritas nele recebem.

Todas as máquinas usam o MESMO broker (MQTT_HOST/PORT/USERNAME/PASSWORD) e o MESMO
TOKEN_REDE_JARVIS — só NOME_MAQUINA muda em cada uma. Toda a lógica fica isolada em
`rede_jarvis/`.

Você também pode perguntar pro ALFRED "quais máquinas estão online?" — cada máquina
avisa quando conecta e o próprio broker avisa automaticamente as outras se ela cair
sem querer (queda de rede, processo morto), sem precisar de nenhuma configuração
extra pra isso.

Onde conseguir cada uma dessas informações:

**MQTT_HOST / MQTT_PORT / MQTT_USERNAME / MQTT_PASSWORD**
Vêm de um broker MQTT na nuvem — o testado neste projeto foi o [HiveMQ Cloud](https://www.hivemq.com/mqtt-cloud-broker/),
que tem um plano gratuito (free/serverless) suficiente pra isso:
1. Crie uma conta e um cluster gratuito no HiveMQ Cloud.
2. No painel do cluster, em "Access Management" (ou "Credentials"), crie um usuário
   com usuário/senha — isso vira MQTT_USERNAME/MQTT_PASSWORD.
3. O endereço do cluster (algo como `xxxxxxxx.s1.eu.hivemq.cloud`) vira MQTT_HOST.
4. A porta TLS (normalmente `8883`) vira MQTT_PORT.
5. Use o MESMO usuário/senha/host em todas as máquinas.

**TOKEN_REDE_JARVIS**
Não vem de lugar nenhum — é uma senha/segredo que você mesmo inventa (quanto mais aleatória e longa, melhor). Ela só precisa ser IGUAL em todas as máquinas, pra elas se reconhecerem entre si e ignorarem qualquer mensagem sem esse segredo. Nunca compartilhe esse valor fora das suas próprias máquinas.

**NOME_MAQUINA**
Também é você quem escolhe: um nome curto pra identificar esse computador (ex: `casa`, `loja`, `escritorio`). É o único valor da lista que muda de uma máquina pra outra.

**PASTA_TRANSFERENCIAS_PADRAO**
Um caminho de pasta no seu computador (ex: `C:\Users\SeuUsuario\Downloads\JarvisRecebidos`) onde arquivos recebidos de outra máquina são salvos automaticamente, caso ninguém responda a tempo ao aviso perguntando onde salvar. Se deixar em branco, o ALFRED usa `Downloads\JarvisRecebidos` por padrão.

**PEDIR_PERMISSAO**
`true` ou `false`. Com `true` (recomendado), todo comando remoto recebido pede confirmação antes de executar — por notificação do Windows ou por voz, se a chamada estiver ativa nesta máquina no momento. Com `false`, comandos remotos executam direto, sem perguntar nada.

**GOOGLE_SERVICE_ACCOUNT_JSON** (opcional — só é necessário se for enviar arquivo maior que 4.5MB entre as máquinas)
O MQTT do HiveMQ Cloud tem um limite de ~5MB por mensagem — arquivos maiores que isso
usam o Google Drive como intermediário automaticamente.
1. Acesse https://console.cloud.google.com/ e crie um projeto novo (ou use um já existente).
2. No menu lateral, vá em "APIs e serviços" → "Biblioteca", procure por "Google Drive API" e clique em "Ativar".
3. Vá em "APIs e serviços" → "Credenciais" → "Criar credenciais" → "Conta de serviço".
4. Dê um nome pra conta de serviço (ex: `jarvis-casa`) e clique em "Concluir" (não precisa conceder nenhum papel/permissão especial).
5. Clique na conta de serviço recém-criada → aba "Chaves" → "Adicionar chave" → "Criar nova chave" → escolha o formato JSON.
6. Um arquivo `.json` vai ser baixado — salve ele em algum lugar seguro do seu computador (NÃO dentro de uma pasta versionada pelo Git) e coloque o caminho completo desse arquivo em `GOOGLE_SERVICE_ACCOUNT_JSON`.
7. Cada máquina precisa da SUA PRÓPRIA conta de serviço — repita esses passos em cada computador, não reaproveite o mesmo arquivo JSON entre máquinas diferentes.

Se você nunca for mandar arquivo maior que 4.5MB entre as máquinas, pode deixar essa variável em branco.

**Atenção**: testando com uma Service Account real, a quota de armazenamento dela veio zerada (`limit: 0`). Contas de serviço de projetos pessoais (fora do Google Workspace) normalmente não têm espaço próprio no Drive — então o upload de arquivo grande pode falhar por falta de quota, mesmo com tudo configurado certo. Se isso acontecer, a solução costuma ser criar um Shared Drive (Drive Compartilhado) no Google Workspace e dar acesso à Service Account nele; isso ainda não foi testado neste projeto.

-------------------------------------------------

Rode o comando:
```
pip install -r requirements.txt
```
--------------------------------------------------

Para o jarvis iniciar a chamada sozinho ao ouvir uma palavra-chave (sem precisar clicar
no botão), você pode opcionalmente adicionar também no .env:
```
NOME_ATIVACAO=jarvis
TIMEOUT_INATIVIDADE_SEGUNDOS=300
```

Nenhuma conta ou chave de API é necessária pra isso — o reconhecimento de voz roda
100% localmente (biblioteca [Vosk](https://alphacephei.com/vosk/), offline, sem enviar
áudio pra nenhum serviço externo). Na primeira vez que o app rodar, o pacote `vosk`
baixa sozinho um modelo de reconhecimento de voz em português (~31MB, uma única vez,
sem cadastro nenhum) e guarda em cache local — as próximas execuções carregam
instantaneamente. Enquanto esse download não termina, a ativação por voz ainda não
está pronta, mas o botão manual de iniciar chamada continua funcionando normalmente.

**NOME_ATIVACAO** (padrão: `jarvis`)
A palavra (ou frase curta) que, reconhecida enquanto nenhuma chamada está ativa, inicia
a chamada automaticamente. Padrão `iniciar chamada`. **Atenção**: como isso usa
reconhecimento de voz genérico (não um motor de "wake word" dedicado), a palavra/frase
precisa existir de fato no vocabulário do modelo Vosk em português — nomes próprios de
origem estrangeira (como "jarvis") costumam NÃO estar nesse vocabulário e nunca vão ser
reconhecidos, não importa quão claramente sejam ditos. Prefira palavras/frases comuns do
dia a dia. A precisão também é um pouco menor que a de um motor de "wake word" dedicado
— pode falhar em detectar vez ou outra, especialmente se pronunciada junto com outras
palavras coladas sem pausa nenhuma.

**TIMEOUT_INATIVIDADE_SEGUNDOS** (padrão: `300`, ou seja, 5 minutos)
Depois de uma chamada ficar esse tempo sem nenhuma atividade real (o jarvis falando ou
executando alguma ação — nunca só ruído captado pelo microfone), ele avisa por voz e
encerra a chamada sozinho.

**Não confunda com a palavra-chave de autenticação DENTRO da chamada** (ver abaixo,
"Coisa") — são coisas diferentes: `NOME_ATIVACAO` decide quando a chamada COMEÇA
(sozinha, por voz, sem clicar no botão); a palavra "Coisa" continua controlando o que o
jarvis executa DEPOIS que a chamada já está em andamento.

--------------------------------------------------

A palavra chave é "Coisa"

Você pode desligar essa exigência (o jarvis passa a responder qualquer comando sem
pedir a palavra-chave) colocando no .env:
```
EXIGIR_AUTENTICACAO=false
```
O padrão, se essa variável não existir no .env, é `true` (exige a palavra-chave, como
sempre foi) — só fica sem exigir se você explicitamente colocar `false`.

Toda vez que uma chamada é iniciada (por clique no botão ou por ativação de voz), o
jarvis toca um beep local assim que conecta — antes mesmo de pedir a palavra-chave,
se `EXIGIR_AUTENTICACAO` estiver ligado. É só um aviso local (não depende do Gemini)
pra você saber que já pode falar; antes disso o jarvis tentava dizer em voz "Chamada
iniciada.", mas isso dependia de uma resposta do modelo (ida e volta até o Gemini +
detecção de fim de fala do lado do servidor) e demorava demais pra cumprir esse papel.
