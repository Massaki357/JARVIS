Crie um arquivo .env e coloque as seguintes API KEYs:

```
GEMINI_API_KEY=

OPENAI_API_KEY=

MISTRAL_API_KEY=

GROQ_API_KEY=

CEREBRAS_API_KEY=
```

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
