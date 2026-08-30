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

Para o ALFRED conseguir mandar comando pra outras máquinas (rede_jarvis, via Telegram),
adicione também no .env:
```
TELEGRAM_BOT_TOKEN=
TOKEN_REDE_JARVIS=
NOME_MAQUINA=
TELEGRAM_CHAT_ID=
PASTA_TRANSFERENCIAS_PADRAO=
GOOGLE_SERVICE_ACCOUNT_JSON=
PEDIR_PERMISSAO=true
```

Todas as máquinas usam o MESMO bot, o MESMO TOKEN_REDE_JARVIS e o MESMO TELEGRAM_CHAT_ID.
NOME_MAQUINA é o único valor que muda em cada máquina. Toda a lógica fica isolada em `rede_jarvis/`.

Onde conseguir cada uma dessas informações:

**TELEGRAM_BOT_TOKEN**
1. Abra o Telegram e procure pelo contato `@BotFather` (é o bot oficial do próprio Telegram pra criar outros bots).
2. Mande o comando `/newbot`.
3. Escolha um nome de exibição (qualquer um) e depois um username, que precisa ser único e terminar em "bot" (ex: `alfred_familia_bot`).
4. O BotFather devolve um token parecido com `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — copie ele inteiro.
5. Use o MESMO bot/token em todas as máquinas que forem rodar o ALFRED.

**TOKEN_REDE_JARVIS**
Não vem de lugar nenhum — é uma senha/segredo que você mesmo inventa (quanto mais aleatória e longa, melhor). Ela só precisa ser IGUAL em todas as máquinas, pra elas se reconhecerem entre si e ignorarem qualquer mensagem sem esse segredo. Nunca compartilhe esse valor fora das suas próprias máquinas.

**NOME_MAQUINA**
Também é você quem escolhe: um nome curto pra identificar esse computador (ex: `casa`, `loja`, `escritorio`). É o único valor da lista que muda de uma máquina pra outra.

**TELEGRAM_CHAT_ID**
1. Se for usar em mais de um computador, crie um grupo no Telegram e adicione o bot nele (procure o username do bot e adicione como membro). Se for usar só numa máquina, pode simplesmente abrir uma conversa direta com o bot.
2. Mande qualquer mensagem de teste nesse chat/grupo (o bot precisa "ver" pelo menos uma mensagem antes de você conseguir descobrir o ID).
3. No navegador, acesse o endereço abaixo, trocando `SEU_TOKEN` pelo token do passo anterior:
```
https://api.telegram.org/botSEU_TOKEN/getUpdates
```
4. Procure por `"chat":{"id":` no JSON que aparece na tela. Se for um grupo, o número vem negativo (ex: `-1001234567890`) — copie ele inteiro, incluindo o sinal de menos.
5. Use o MESMO chat_id em todas as máquinas.

**PASTA_TRANSFERENCIAS_PADRAO**
Um caminho de pasta no seu computador (ex: `C:\Users\SeuUsuario\Downloads\JarvisRecebidos`) onde arquivos recebidos de outra máquina são salvos automaticamente, caso ninguém responda a tempo ao aviso perguntando onde salvar. Se deixar em branco, o ALFRED usa `Downloads\JarvisRecebidos` por padrão.

**PEDIR_PERMISSAO**
`true` ou `false`. Com `true` (recomendado), todo comando remoto recebido pede confirmação antes de executar — por notificação do Windows ou por voz, se a chamada estiver ativa nesta máquina no momento. Com `false`, comandos remotos executam direto, sem perguntar nada.

**GOOGLE_SERVICE_ACCOUNT_JSON** (opcional — só é necessário se for enviar arquivo maior que 50MB entre as máquinas)
1. Acesse https://console.cloud.google.com/ e crie um projeto novo (ou use um já existente).
2. No menu lateral, vá em "APIs e serviços" → "Biblioteca", procure por "Google Drive API" e clique em "Ativar".
3. Vá em "APIs e serviços" → "Credenciais" → "Criar credenciais" → "Conta de serviço".
4. Dê um nome pra conta de serviço (ex: `jarvis-casa`) e clique em "Concluir" (não precisa conceder nenhum papel/permissão especial).
5. Clique na conta de serviço recém-criada → aba "Chaves" → "Adicionar chave" → "Criar nova chave" → escolha o formato JSON.
6. Um arquivo `.json` vai ser baixado — salve ele em algum lugar seguro do seu computador (NÃO dentro de uma pasta versionada pelo Git) e coloque o caminho completo desse arquivo em `GOOGLE_SERVICE_ACCOUNT_JSON`.
7. Cada máquina precisa da SUA PRÓPRIA conta de serviço — repita esses passos em cada computador, não reaproveite o mesmo arquivo JSON entre máquinas diferentes.

Se você nunca for mandar arquivo maior que 50MB entre as máquinas, pode deixar essa variável em branco.

-------------------------------------------------

Rode o comando:
```
pip install google-genai PySide6 python-dotenv sounddevice numpy mss opencv-python pillow
```
ou
```
pip install -r requirements.txt
```
--------------------------------------------------

A palavra chave é "Coisa"
