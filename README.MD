# ALFRED

Assistente de voz para desktop Windows, construído com PySide6 e a Gemini Live API (`google-genai`). O ALFRED conversa em tempo real por voz, em português do Brasil, e pode executar ações no computador quando solicitado.

## O que o ALFRED sabe fazer

- **Conversar por voz em tempo real**, com autenticação por palavra-chave antes de qualquer interação.
- **Analisar a tela ou a webcam** quando pedido (por voz ou pelos botões da interface).
- **Localizar e clicar em elementos na tela** descritos por voz ("clique em Continuar", "clique no botão vermelho"), com verificação de confiança e bloqueio de ações sensíveis (excluir, comprar, pagar, instalar, etc.).
- **Gerenciar a Área de Trabalho**: criar pastas, listar, organizar arquivos por tipo, copiar/recortar/colar e renomear — sem nunca excluir ou sobrescrever nada.
- **Abrir aplicativos e recursos do Windows** (navegador, calculadora, configurações, Explorador de Arquivos, pastas pessoais, apps da Microsoft Store, etc.).
- **Pesquisar no navegador** (Google) e **tocar vídeos/músicas no YouTube**.
- **Responder com informações atuais** (cotação, clima, notícias, placares...) fazendo uma pesquisa invisível na internet só quando realmente necessário — sem abrir nenhuma janela.
- **Controlar o mouse** (rolar a página, clicar, clique duplo, clique direito).
- **Escrever texto no campo ativo** do Windows, onde o cursor estiver.
- **Manter uma agenda local persistente** de compromissos (criar, listar, cancelar).
- **Lembrar informações entre sessões** (memória persistente: salvar, listar, esquecer).
- **Encerrar a chamada por comando de voz.**

Todas essas ações só são executadas quando o usuário pede explicitamente — nada é acionado espontaneamente pelo modelo.

Para saber exatamente o que cada arquivo do projeto faz, veja **[`ARCHITECTURE.md`](ARCHITECTURE.md)**. Para instruções voltadas a quem for editar o código com o Claude Code, veja **[`CLAUDE.md`](CLAUDE.md)**.

## Instalação

1. Crie um arquivo `.env` na raiz do projeto com sua chave da API do Gemini:
   ```
   GEMINI_API_KEY=<sua chave aqui>
   ```

2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

3. Rode o assistente:
   ```
   python main.py
   ```

## Palavra-chave

O ALFRED só interage após ouvir a palavra-chave de autenticação: **"Coisa"**.
