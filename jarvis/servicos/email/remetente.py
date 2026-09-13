import smtplib
from email.message import EmailMessage

import mimetypes

import os

from dotenv import load_dotenv

load_dotenv()

LIMITE_ANEXO_MB = 18

EMAIL_SMTP_HOST = os.getenv(
    "EMAIL_SMTP_HOST",
    "smtp.gmail.com",
)
EMAIL_SMTP_PORT = int(
    os.getenv(
        "EMAIL_SMTP_PORT",
        "587",
    )
)
EMAIL_REMETENTE = os.getenv(
    "EMAIL_REMETENTE"
)
EMAIL_SENHA_APP = os.getenv(
    "EMAIL_SENHA_APP"
)


def config_schema():
    return [
        {
            "nome": "EMAIL_SMTP_HOST",
            "rotulo": "Servidor SMTP (padrão: smtp.gmail.com)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EMAIL_SMTP_PORT",
            "rotulo": "Porta SMTP (padrão: 587)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EMAIL_REMETENTE",
            "rotulo": "Endereço de email remetente (usado também para ler emails)",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "EMAIL_SENHA_APP",
            "rotulo": "Senha de aplicativo (nunca a senha normal da conta)",
            "sensivel": True,
            "obrigatoria": True,
        },
    ]


def enviar_email(
    destinatario,
    assunto,
    corpo,
    caminho_anexo=None,
):
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

    if caminho_anexo:
        if not os.path.isfile(caminho_anexo):
            return (
                f"Arquivo de anexo não encontrado: {caminho_anexo}"
            )

        tamanho_mb = os.path.getsize(caminho_anexo) / (1024 * 1024)

        if tamanho_mb > LIMITE_ANEXO_MB:
            return (
                f"O arquivo '{os.path.basename(caminho_anexo)}' tem "
                f"{tamanho_mb:.1f} MB, acima do limite de "
                f"{LIMITE_ANEXO_MB} MB aceito para anexos (a maioria "
                "dos provedores de email recusaria o envio). Escolha "
                "um arquivo menor ou compartilhe por outro meio."
            )

    mensagem = EmailMessage()
    mensagem["From"] = EMAIL_REMETENTE
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(
        corpo
    )

    if caminho_anexo:
        tipo_mime, _codificacao = mimetypes.guess_type(caminho_anexo)
        maintype, subtype = (
            tipo_mime.split("/", 1)
            if tipo_mime
            else ("application", "octet-stream")
        )

        try:
            with open(caminho_anexo, "rb") as arquivo:
                conteudo_anexo = arquivo.read()

        except OSError as erro:
            return (
                f"Falha ao ler o arquivo de anexo '{caminho_anexo}': "
                f"{erro}"
            )

        mensagem.add_attachment(
            conteudo_anexo,
            maintype=maintype,
            subtype=subtype,
            filename=os.path.basename(caminho_anexo),
        )

    try:
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

    texto_anexo = (
        f" com o arquivo '{os.path.basename(caminho_anexo)}' em anexo"
        if caminho_anexo
        else ""
    )

    return (
        f"Email enviado para {destinatario} "
        f"com o assunto '{assunto}'{texto_anexo}."
    )
