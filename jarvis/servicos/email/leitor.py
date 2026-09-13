import imaplib
import email
from email.header import decode_header
import re

import os
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EMAIL_IMAP_HOST = os.getenv(
    "EMAIL_IMAP_HOST",
    "imap.gmail.com",
)
EMAIL_IMAP_PORT = int(
    os.getenv(
        "EMAIL_IMAP_PORT",
        "993",
    )
)
EMAIL_REMETENTE = os.getenv(
    "EMAIL_REMETENTE"
)
EMAIL_SENHA_APP = os.getenv(
    "EMAIL_SENHA_APP"
)

LIMITE_MAXIMO_EMAILS = 20

PASTA_DOWNLOADS_EMAIL = Path(
    os.getenv(
        "PASTA_DOWNLOADS_EMAIL",
        str(Path.home() / "Downloads" / "JarvisEmail"),
    )
)


def config_schema():
    return [
        {
            "nome": "EMAIL_IMAP_HOST",
            "rotulo": "Servidor IMAP (padrão: imap.gmail.com)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EMAIL_IMAP_PORT",
            "rotulo": "Porta IMAP (padrão: 993)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EMAIL_REMETENTE",
            "rotulo": "Endereço de email remetente (usado também para enviar emails)",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "EMAIL_SENHA_APP",
            "rotulo": "Senha de aplicativo (nunca a senha normal da conta)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "PASTA_DOWNLOADS_EMAIL",
            "rotulo": (
                "Pasta onde anexos baixados são salvos "
                "(padrão: Downloads/JarvisEmail)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]


def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


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


PASTA_SPAM_PADRAO = "[Gmail]/Spam"


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


def _resolver_nome_pasta(
    servidor,
    pasta,
):
    if isinstance(pasta, str) and pasta.strip().upper() == "SPAM":
        return _resolver_pasta_spam(
            servidor
        )

    return "INBOX"


@contextmanager
def _sessao_imap(pasta="INBOX"):
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

        status_select, _ = servidor.select(
            nome_pasta,
            readonly=True,
        )

        if status_select != "OK":
            raise RuntimeError(
                f"Não foi possível acessar a pasta '{nome_pasta}'."
            )

        yield servidor


def _buscar_emails_recentes(servidor, quantidade):
    status, dados = servidor.search(
        None,
        "ALL",
    )

    if status != "OK":
        raise RuntimeError(
            "Não foi possível consultar a caixa de entrada."
        )

    ids = dados[0].split()

    if not ids:
        return []

    ids_recentes = ids[-quantidade:][::-1]

    resultado = []

    for id_email in ids_recentes:
        status, dados_msg = servidor.fetch(
            id_email,
            "(BODY.PEEK[])",
        )

        if (
            status != "OK"
            or not dados_msg
            or not dados_msg[0]
        ):
            continue

        mensagem = email.message_from_bytes(
            dados_msg[0][1]
        )

        resultado.append(
            {
                "id_email": id_email,
                "remetente": _decodificar_cabecalho(
                    mensagem.get("From", "Desconhecido")
                ),
                "assunto": _decodificar_cabecalho(
                    mensagem.get("Subject", "(sem assunto)")
                ),
                "data": mensagem.get("Date", ""),
                "anexos": _listar_nomes_anexos(mensagem),
                "mensagem": mensagem,
            }
        )

    return resultado


def _listar_nomes_anexos(mensagem):
    nomes = []

    for parte in mensagem.walk():
        if (
            parte.get_content_disposition() == "attachment"
            and parte.get_filename()
        ):
            nomes.append(
                _nome_arquivo_seguro(
                    _decodificar_cabecalho(
                        parte.get_filename()
                    )
                )
            )

    return nomes


def _nome_arquivo_seguro(nome_bruto):
    nome = os.path.basename(
        (nome_bruto or "").strip()
    )

    nome = nome.lstrip(".")

    nome = re.sub(
        r"[^A-Za-z0-9._\- ]",
        "_",
        nome,
    )

    return nome.strip() or "anexo"


def ler_emails(
    quantidade=5,
    apenas_nao_lidos=False,
    pasta="INBOX",
):
    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return (
            "Configuração de email ausente. Defina EMAIL_REMETENTE "
            "e EMAIL_SENHA_APP no arquivo .env antes de ler emails."
        )

    if not isinstance(quantidade, int) or quantidade <= 0:
        quantidade = 5

    quantidade = min(
        quantidade,
        LIMITE_MAXIMO_EMAILS,
    )

    pasta_amigavel = (
        "pasta de spam"
        if isinstance(pasta, str) and pasta.strip().upper() == "SPAM"
        else "caixa de entrada"
    )

    try:
        with _sessao_imap(pasta) as servidor:
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

            ids_recentes = ids[-quantidade:][::-1]

            linhas = []

            for numero, id_email in enumerate(
                ids_recentes,
                start=1,
            ):
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

    except RuntimeError as erro:
        return str(erro)

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


def listar_anexos_disponiveis(quantidade=10):
    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return (
            "Configuração de email ausente. Defina EMAIL_REMETENTE "
            "e EMAIL_SENHA_APP no arquivo .env antes de acessar "
            "emails."
        )

    if not isinstance(quantidade, int) or quantidade <= 0:
        quantidade = 10

    quantidade = min(
        quantidade,
        LIMITE_MAXIMO_EMAILS,
    )

    try:
        with _sessao_imap("INBOX") as servidor:
            emails = _buscar_emails_recentes(
                servidor,
                quantidade,
            )

    except RuntimeError as erro:
        return str(erro)

    except imaplib.IMAP4.error as erro:
        return f"Falha ao acessar a caixa de entrada: {erro}"

    except OSError as erro:
        return f"Falha de conexão com o servidor de email: {erro}"

    com_anexo = [
        item
        for item in emails
        if item["anexos"]
    ]

    if not com_anexo:
        return "Nenhum dos emails recentes tem anexo."

    linhas = [
        f"De: {item['remetente']} | Assunto: {item['assunto']} | "
        f"Data: {item['data']} | Anexo(s): "
        + ", ".join(item["anexos"])
        for item in com_anexo
    ]

    return (
        "Emails recentes com anexo:\n"
        + "\n".join(linhas)
    )


def baixar_anexo(criterio_busca, nome_arquivo=None):
    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return (
            "Configuração de email ausente. Defina EMAIL_REMETENTE "
            "e EMAIL_SENHA_APP no arquivo .env antes de acessar "
            "emails."
        )

    if not isinstance(criterio_busca, str) or not criterio_busca.strip():
        return (
            "É necessário informar o remetente, o assunto, ou "
            "'mais recente' para saber de qual email baixar o anexo."
        )

    alvo_normalizado = _normalizar(criterio_busca)

    pede_mais_recente = alvo_normalizado in (
        "mais recente",
        "recente",
        "ultimo",
        "ultimo email",
        "ultimo anexo",
    )

    try:
        with _sessao_imap("INBOX") as servidor:
            emails = _buscar_emails_recentes(
                servidor,
                LIMITE_MAXIMO_EMAILS,
            )

    except RuntimeError as erro:
        return str(erro)

    except imaplib.IMAP4.error as erro:
        return f"Falha ao acessar a caixa de entrada: {erro}"

    except OSError as erro:
        return f"Falha de conexão com o servidor de email: {erro}"

    com_anexo = [
        item
        for item in emails
        if item["anexos"]
    ]

    if not com_anexo:
        return "Não encontrei nenhum email recente com anexo."

    if pede_mais_recente:
        candidatos = com_anexo[:1]

    else:
        candidatos = _filtrar_emails_por_criterio(
            com_anexo,
            criterio_busca,
        )

    if not candidatos:
        return (
            f"Não encontrei nenhum email correspondente a "
            f"'{criterio_busca}' com anexo."
        )

    if len(candidatos) > 1:
        linhas = [
            f"De: {item['remetente']} | Assunto: {item['assunto']} "
            f"| Data: {item['data']}"
            for item in candidatos[:5]
        ]

        return (
            "Encontrei mais de um email correspondente com anexo:\n"
            + "\n".join(linhas)
            + "\nQual deles?"
        )

    return _salvar_anexos_do_email(
        candidatos[0],
        nome_arquivo,
    )


def _filtrar_emails_por_criterio(emails, criterio_busca):
    alvo = _normalizar(criterio_busca)

    exatos = [
        item
        for item in emails
        if _normalizar(item["remetente"]) == alvo
        or _normalizar(item["assunto"]) == alvo
    ]

    if exatos:
        return exatos

    parciais = [
        item
        for item in emails
        if alvo in _normalizar(item["remetente"])
        or alvo in _normalizar(item["assunto"])
    ]

    return parciais


def _salvar_anexos_do_email(email_alvo, nome_arquivo):
    anexos_disponiveis = email_alvo["anexos"]

    nomes_para_salvar = anexos_disponiveis

    if nome_arquivo:
        alvo_normalizado = _normalizar(nome_arquivo)

        correspondentes = [
            nome
            for nome in anexos_disponiveis
            if _normalizar(nome) == alvo_normalizado
            or alvo_normalizado in _normalizar(nome)
        ]

        if not correspondentes:
            return (
                f"O email de {email_alvo['remetente']} (assunto: "
                f"{email_alvo['assunto']}) não tem nenhum anexo "
                f"chamado '{nome_arquivo}'. Anexos disponíveis: "
                + ", ".join(anexos_disponiveis)
                + "."
            )

        nomes_para_salvar = correspondentes

    try:
        PASTA_DOWNLOADS_EMAIL.mkdir(
            parents=True,
            exist_ok=True,
        )

    except OSError as erro:
        return f"Falha ao preparar a pasta de downloads: {erro}"

    caminhos_salvos = []

    for parte in email_alvo["mensagem"].walk():
        if parte.get_content_disposition() != "attachment":
            continue

        nome_bruto = parte.get_filename()

        if not nome_bruto:
            continue

        nome_seguro = _nome_arquivo_seguro(
            _decodificar_cabecalho(nome_bruto)
        )

        if nome_seguro not in nomes_para_salvar:
            continue

        conteudo = parte.get_payload(decode=True)

        if conteudo is None:
            continue

        caminho_destino = _caminho_sem_sobrescrever(
            PASTA_DOWNLOADS_EMAIL / nome_seguro
        )

        base_resolvida = PASTA_DOWNLOADS_EMAIL.resolve()
        destino_resolvido = caminho_destino.resolve()

        if base_resolvida not in destino_resolvido.parents:
            continue

        try:
            with open(caminho_destino, "wb") as arquivo:
                arquivo.write(conteudo)

        except OSError as erro:
            return (
                f"Falha ao salvar '{nome_decodificado}': {erro}"
            )

        caminhos_salvos.append(str(caminho_destino))

    if not caminhos_salvos:
        return (
            "Não consegui salvar o(s) anexo(s) — conteúdo vazio ou "
            "inacessível."
        )

    return (
        "Anexo(s) salvo(s) com sucesso: "
        + "; ".join(caminhos_salvos)
        + ". O conteúdo não foi aberto nem executado automaticamente "
        "— trate como não confiável até verificar você mesmo."
    )


def _caminho_sem_sobrescrever(caminho):
    if not caminho.exists():
        return caminho

    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidato = caminho.with_stem(f"{caminho.stem}_{sufixo}")

    contador = 1

    while candidato.exists():
        candidato = caminho.with_stem(
            f"{caminho.stem}_{sufixo}_{contador}"
        )
        contador += 1

    return candidato
