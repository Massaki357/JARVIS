# smtplib é a biblioteca padrão do Python para enviar
# emails usando o protocolo SMTP.
import smtplib
# EmailMessage monta o cabeçalho e o corpo do email de forma simples
# — inclusive anexos, via add_attachment(), sem precisar montar a
# estrutura MIME multipart manualmente com email.mime.*.
from email.message import EmailMessage

# Usado só para adivinhar o tipo MIME (maintype/subtype) do anexo
# a partir da extensão do arquivo — biblioteca padrão.
import mimetypes

import os

# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

load_dotenv()

# Tamanho máximo de anexo aceito, em MB, ANTES da codificação
# base64 do email (que infla o tamanho em ~37%). A maioria dos
# provedores SMTP recusa mensagens acima de ~25MB já codificadas —
# 18MB de arquivo bruto fica com boa margem abaixo disso depois de
# codificado (18 * 1.37 ≈ 24.7MB).
LIMITE_ANEXO_MB = 18

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


# Envia um email simples em texto puro, com anexo opcional.
# Retorna sempre uma mensagem em português descrevendo o
# resultado, pronta para ser falada ou exibida por quem chamar.
def enviar_email(
    destinatario,
    assunto,
    corpo,
    caminho_anexo=None,
):
    """
    Envia um email via SMTP usando as credenciais configuradas
    no .env (EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT).

    caminho_anexo, se informado, é o caminho absoluto de um arquivo
    local a anexar à mensagem. É validado (existe? não excede
    LIMITE_ANEXO_MB?) antes de qualquer tentativa de envio.

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

    # Monta a mensagem com remetente, destinatário,
    # assunto e corpo em texto puro.
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

    texto_anexo = (
        f" com o arquivo '{os.path.basename(caminho_anexo)}' em anexo"
        if caminho_anexo
        else ""
    )

    return (
        f"Email enviado para {destinatario} "
        f"com o assunto '{assunto}'{texto_anexo}."
    )
