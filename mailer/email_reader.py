# imaplib é a biblioteca padrão do Python para ler emails
# usando o protocolo IMAP.
import imaplib
# email interpreta as mensagens brutas recebidas via IMAP,
# separando cabeçalhos como remetente, assunto e data.
import email
# decode_header decodifica cabeçalhos que vêm codificados
# (comum em assuntos e remetentes com acentos).
from email.header import decode_header
# re é usado para extrair o nome da pasta de spam a partir
# da resposta do comando LIST do IMAP.
import re

import os

# Carrega as variáveis de ambiente do arquivo .env.
from dotenv import load_dotenv

load_dotenv()

# Servidor IMAP usado para leitura. O padrão é o do Gmail,
# mas pode ser trocado no .env para outro provedor.
EMAIL_IMAP_HOST = os.getenv(
    "EMAIL_IMAP_HOST",
    "imap.gmail.com",
)
# Porta do servidor IMAP. 993 é a porta padrão para IMAP sobre SSL.
EMAIL_IMAP_PORT = int(
    os.getenv(
        "EMAIL_IMAP_PORT",
        "993",
    )
)
# Reaproveita as mesmas credenciais usadas pelo envio de email
# (email_sender.py): no Gmail, a mesma senha de aplicativo
# autentica tanto SMTP quanto IMAP.
EMAIL_REMETENTE = os.getenv(
    "EMAIL_REMETENTE"
)
EMAIL_SENHA_APP = os.getenv(
    "EMAIL_SENHA_APP"
)

# Quantidade máxima de emails retornados em uma única consulta,
# mesmo que um valor maior seja solicitado.
LIMITE_MAXIMO_EMAILS = 20


# Decodifica um cabeçalho de email (remetente, assunto) que pode
# vir em partes com codificações diferentes.
def _decodificar_cabecalho(valor):
    if not valor:
        return ""

    partes = decode_header(valor)

    texto = ""

    for parte, codificacao in partes:
        if isinstance(parte, bytes):
            texto += parte.decode(
                codificacao or "utf-8",
                errors="replace",
            )

        else:
            texto += parte

    return texto


# Nome de pasta usado como retorno de segurança quando a busca
# dinâmica pela pasta de spam falhar. É o nome padrão do Gmail,
# mas pode não existir em contas com outro idioma.
PASTA_SPAM_PADRAO = "[Gmail]/Spam"


# Descobre o nome real da pasta de spam via o comando LIST do
# IMAP, procurando a pasta marcada com a flag especial \Junk.
# Isso evita depender de um nome fixo, que muda conforme o
# idioma da conta (ex: "[Gmail]/Spam" ou "[Gmail]/Lixo Eletrônico").
def _resolver_pasta_spam(servidor):
    status, pastas = servidor.list()

    if status == "OK":
        for linha in pastas:
            if not linha:
                continue

            texto = linha.decode(
                errors="replace",
            )

            if "\\Junk" in texto:
                encontrado = re.search(
                    r'"([^"]*)"\s*$',
                    texto,
                )

                if encontrado:
                    return encontrado.group(1)

    return PASTA_SPAM_PADRAO


# Traduz o valor recebido em "pasta" (INBOX ou SPAM) para o
# nome de pasta real usado pelo comando SELECT do IMAP.
def _resolver_nome_pasta(
    servidor,
    pasta,
):
    if isinstance(pasta, str) and pasta.strip().upper() == "SPAM":
        return _resolver_pasta_spam(
            servidor
        )

    return "INBOX"


# Lista os emails mais recentes de uma pasta da caixa postal
# (caixa de entrada ou spam), mostrando remetente, assunto e
# data de cada um.
# Retorna sempre uma mensagem em português, pronta para ser
# falada ou exibida por quem chamar.
def ler_emails(
    quantidade=5,
    apenas_nao_lidos=False,
    pasta="INBOX",
):
    """
    Lê uma pasta da caixa postal via IMAP usando as credenciais
    configuradas no .env (EMAIL_REMETENTE, EMAIL_SENHA_APP,
    EMAIL_IMAP_HOST, EMAIL_IMAP_PORT).

    O parâmetro "pasta" aceita "INBOX" (padrão, caixa de entrada)
    ou "SPAM" (pasta de spam/lixo eletrônico, localizada
    automaticamente pela flag \\Junk do servidor IMAP).

    Abre a conexão em modo somente leitura e busca os cabeçalhos
    com BODY.PEEK, para nunca marcar mensagens como lidas apenas
    por listá-las.

    Este módulo não depende do restante do projeto: usa apenas a
    biblioteca padrão do Python e python-dotenv, podendo ser
    copiado para outro projeto sem alterações.
    """

    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return (
            "Configuração de email ausente. Defina EMAIL_REMETENTE "
            "e EMAIL_SENHA_APP no arquivo .env antes de ler emails."
        )

    if not isinstance(quantidade, int) or quantidade <= 0:
        quantidade = 5

    # Limita a quantidade solicitada para evitar consultas
    # excessivamente grandes.
    quantidade = min(
        quantidade,
        LIMITE_MAXIMO_EMAILS,
    )

    # Descrição da pasta em português, usada nas mensagens de
    # retorno faladas para o usuário.
    pasta_amigavel = (
        "pasta de spam"
        if isinstance(pasta, str) and pasta.strip().upper() == "SPAM"
        else "caixa de entrada"
    )

    try:
        with imaplib.IMAP4_SSL(
            EMAIL_IMAP_HOST,
            EMAIL_IMAP_PORT,
        ) as servidor:
            servidor.login(
                EMAIL_REMETENTE,
                EMAIL_SENHA_APP,
            )

            nome_pasta = _resolver_nome_pasta(
                servidor,
                pasta,
            )

            # readonly=True garante que nenhuma mensagem seja
            # alterada só por estarmos consultando a caixa.
            status_select, _ = servidor.select(
                nome_pasta,
                readonly=True,
            )

            if status_select != "OK":
                return (
                    f"Não foi possível acessar a {pasta_amigavel}."
                )

            criterio = (
                "UNSEEN" if apenas_nao_lidos else "ALL"
            )

            status, dados = servidor.search(
                None,
                criterio,
            )

            if status != "OK":
                return (
                    f"Não foi possível consultar a {pasta_amigavel}."
                )

            ids = dados[0].split()

            if not ids:
                return (
                    f"Nenhum email não lido encontrado na {pasta_amigavel}."
                    if apenas_nao_lidos
                    else f"A {pasta_amigavel} está vazia."
                )

            # IMAP retorna os IDs em ordem crescente (mais antigos
            # primeiro). Pegamos os últimos e invertemos para
            # mostrar do mais recente para o mais antigo.
            ids_recentes = ids[-quantidade:][::-1]

            linhas = []

            for numero, id_email in enumerate(
                ids_recentes,
                start=1,
            ):
                # BODY.PEEK busca apenas os cabeçalhos pedidos e
                # não marca a mensagem como lida.
                status, dados_msg = servidor.fetch(
                    id_email,
                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
                )

                if (
                    status != "OK"
                    or not dados_msg
                    or not dados_msg[0]
                ):
                    continue

                cabecalhos = email.message_from_bytes(
                    dados_msg[0][1]
                )

                remetente = _decodificar_cabecalho(
                    cabecalhos.get(
                        "From",
                        "Desconhecido",
                    )
                )

                assunto = _decodificar_cabecalho(
                    cabecalhos.get(
                        "Subject",
                        "(sem assunto)",
                    )
                )

                data = cabecalhos.get(
                    "Date",
                    "",
                )

                linhas.append(
                    f"{numero}. De: {remetente} | "
                    f"Assunto: {assunto} | Data: {data}"
                )

    except imaplib.IMAP4.error as erro:
        return (
            f"Falha ao acessar a {pasta_amigavel}: {erro}"
        )

    except OSError as erro:
        return (
            f"Falha de conexão com o servidor de email: {erro}"
        )

    if not linhas:
        return (
            "Não foi possível ler os emails encontrados."
        )

    return (
        f"Últimos emails na {pasta_amigavel}:\n"
        + "\n".join(linhas)
    )
