Crie um arquivo .env e coloque as seguintes API KEYs:

```
GEMINI_API_KEY=

OPENAI_API_KEY=

MISTRAL_API_KEY=

GROQ_API_KEY=

CEREBRAS_API_KEY=
```

Para o ALFRED conseguir enviar emails, adicione também no .env:
```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_REMETENTE=seu-email@gmail.com
EMAIL_SENHA_APP=sua-senha-de-app (não é a senha normal da conta)
```

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
