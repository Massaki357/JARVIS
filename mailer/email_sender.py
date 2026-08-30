# smtplib é a biblioteca padrão do Python para enviar
# emails usando o protocolo SMTP.
import smtplib
# EmailMessage monta o cabeçalho e o corpo do email
# de forma simples, sem precisar montar texto MIME manualmente.
from email.message import EmailMessage

import os

# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

load_dotenv()

# Servidor SMTP usado para o envio. O padrão é o do Gmail,
# mas pode ser trocado no .env para outro provedor.
EMAIL_SMTP_HOST = os.getenv(
    "EMAIL_SMTP_HOST",
    "smtp.gmail.com",
)
# Porta do servidor SMTP. 587 é a porta padrão para STARTTLS.
EMAIL_SMTP_PORT = int(
    os.getenv(
        "EMAIL_SMTP_PORT",
        "587",
    )
)
# Endereço que aparece como remetente e usado para autenticação.
EMAIL_REMETENTE = os.getenv(
    "EMAIL_REMETENTE"
)
# Senha de aplicativo da conta de email (nunca a senha normal
# da conta). Para Gmail, é gerada em myaccount.google.com/apppasswords.
EMAIL_SENHA_APP = os.getenv(
    "EMAIL_SENHA_APP"
)


# Envia um email simples em texto puro.
# Retorna sempre uma mensagem em português descrevendo o
# resultado, pronta para ser falada ou exibida por quem chamar.
def enviar_email(
    destinatario,
    assunto,
    corpo,
):
    """
    Envia um email via SMTP usando as credenciais configuradas
    no .env (EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT).

    Este módulo não depende do restante do projeto: usa apenas
    a biblioteca padrão do Python e python-dotenv, podendo ser
    copiado para outro projeto sem alterações.
    """

    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return (
            "Configuração de email ausente. Defina EMAIL_REMETENTE "
            "e EMAIL_SENHA_APP no arquivo .env antes de enviar emails."
        )

    if not isinstance(destinatario, str) or "@" not in destinatario:
        return (
            "Endereço de email do destinatário inválido ou ausente."
        )

    if not isinstance(assunto, str) or not assunto.strip():
        return (
            "É necessário informar um assunto para o email."
        )

    if not isinstance(corpo, str) or not corpo.strip():
        return (
            "É necessário informar o conteúdo do email."
        )

    # Monta a mensagem com remetente, destinatário,
    # assunto e corpo em texto puro.
    mensagem = EmailMessage()
    mensagem["From"] = EMAIL_REMETENTE
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(
        corpo
    )

    try:
        # Abre a conexão SMTP e faz upgrade para TLS antes
        # de autenticar, protegendo login e senha em trânsito.
        with smtplib.SMTP(
            EMAIL_SMTP_HOST,
            EMAIL_SMTP_PORT,
        ) as servidor:
            servidor.starttls()

            servidor.login(
                EMAIL_REMETENTE,
                EMAIL_SENHA_APP,
            )

            servidor.send_message(
                mensagem
            )

    except smtplib.SMTPException as erro:
        return (
            f"Falha ao enviar o email: {erro}"
        )

    except OSError as erro:
        return (
            f"Falha de conexão com o servidor de email: {erro}"
        )

    return (
        f"Email enviado para {destinatario} "
        f"com o assunto '{assunto}'."
    )
