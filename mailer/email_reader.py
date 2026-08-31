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
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

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

# Pasta local onde os anexos baixados são salvos. Mesma ideia de
# rede_jarvis.config.PASTA_TRANSFERENCIAS_PADRAO — se não vier
# preenchida no .env, usa uma pasta padrão razoável dentro de
# Downloads.
PASTA_DOWNLOADS_EMAIL = Path(
    os.getenv(
        "PASTA_DOWNLOADS_EMAIL",
        str(Path.home() / "Downloads" / "JarvisEmail"),
    )
)


# Padroniza um texto para facilitar comparações aproximadas (mesmo
# approach já usado em memory_manager.py e
# casa_inteligente/dispositivos_tuya.py): minúsculas, sem acento,
# sem espaço duplicado. Copiado aqui em vez de importado de outro
# pacote de propósito — este módulo é deliberadamente standalone
# (ver docstring de ler_emails), sem depender do resto do projeto.
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


# Conecta, autentica e seleciona a pasta indicada — usado por
# ler_emails, listar_anexos_disponiveis e baixar_anexo, pra nunca
# duplicar a lógica de conexão/autenticação em mais de um lugar.
# Levanta RuntimeError (mensagem já em português, pronta pra virar
# retorno de quem chamou) se a seleção da pasta falhar. Quem chama
# continua responsável por checar EMAIL_REMETENTE/EMAIL_SENHA_APP
# antes e por tratar imaplib.IMAP4.error/OSError ao redor do "with"
# — esta função só cobre a parte que era duplicada entre as três.
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

        # readonly=True garante que nenhuma mensagem seja alterada
        # só por estarmos consultando a caixa.
        status_select, _ = servidor.select(
            nome_pasta,
            readonly=True,
        )

        if status_select != "OK":
            raise RuntimeError(
                f"Não foi possível acessar a pasta '{nome_pasta}'."
            )

        yield servidor


# Busca os `quantidade` emails mais recentes de uma sessão IMAP já
# aberta (mais recente primeiro), com remetente/assunto/data
# decodificados e a lista de nomes de anexo de cada um. Sempre baixa
# a mensagem inteira via BODY.PEEK (nunca marca como lida) porque
# não há como descobrir nome de anexo sem inspecionar a estrutura
# MIME completa — usado por listar_anexos_disponiveis e baixar_anexo,
# que precisam da mesma busca (a segunda reaproveita inclusive o
# objeto email.message.Message já parseado, pra não buscar de novo
# na hora de salvar o anexo).
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


# Percorre as partes MIME de uma mensagem já parseada e retorna os
# nomes (decodificados e sanitizados — ver _nome_arquivo_seguro) de
# tudo marcado como anexo.
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


# O nome de um anexo vem do cabeçalho Content-Disposition da
# mensagem — controlado inteiramente por quem enviou o email, nunca
# confiável. Sem isso, um nome malicioso (ex: "../../.env" ou um
# caminho absoluto) usado direto em PASTA_DOWNLOADS_EMAIL / nome
# permitiria escrever fora da pasta de downloads (path traversal) —
# pathlib inclusive descarta o lado esquerdo do "/" se o direito for
# um caminho absoluto, o que agravaria o problema. Reduz o nome ao
# basename e troca qualquer caractere fora de um conjunto seguro por
# "_", sanitizando de uma vez só na origem (aqui), pra listagem,
# correspondência e salvamento usarem sempre o mesmo nome já seguro.
def _nome_arquivo_seguro(nome_bruto):
    nome = os.path.basename(
        (nome_bruto or "").strip()
    )

    # Impede nomes tipo "." ou ".." sobrando depois do basename, e
    # arquivos ocultos criados sem querer por um nome começando com
    # ponto.
    nome = nome.lstrip(".")

    nome = re.sub(
        r"[^A-Za-z0-9._\- ]",
        "_",
        nome,
    )

    return nome.strip() or "anexo"


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


# Lista os emails recentes da caixa de entrada que têm pelo menos um
# anexo, mostrando remetente, assunto, data e o(s) nome(s) do(s)
# anexo(s) — sem baixar nada, só mostrando o que está disponível.
# Retorna sempre uma mensagem em português, pronta para ser falada.
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


# Encontra o email correspondente a criterio_busca (remetente,
# assunto, ou "mais recente"/"último") entre os recentes que têm
# anexo, e baixa o(s) anexo(s) pra PASTA_DOWNLOADS_EMAIL.
# Retorna sempre uma mensagem em português: sucesso com o(s)
# caminho(s) salvo(s), lista de candidatos pra desambiguar (nunca
# escolhe sozinho), ou explicação clara de por que nada foi
# encontrado.
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
        # _buscar_emails_recentes já devolve do mais recente para o
        # mais antigo.
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


# Filtra emails por remetente OU assunto batendo com criterio_busca
# — mesmo padrão de resolução aproximada (exato primeiro, depois
# parcial em qualquer direção, acento/caixa insensível) já usado em
# casa_inteligente/dispositivos_tuya.py:resolver_dispositivo.
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


# Salva o(s) anexo(s) do email já localizado em PASTA_DOWNLOADS_EMAIL.
# Se nome_arquivo for informado, salva só o anexo correspondente
# (mesma resolução aproximada); senão, salva todos os anexos do
# email. Nunca sobrescreve um arquivo existente — adiciona um sufixo
# de data/hora (e um contador, se ainda colidir).
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

    # O conteúdo do anexo só existe nas partes de verdade da
    # mensagem — os nomes em "anexos" vieram de uma passada anterior
    # (_listar_nomes_anexos), então percorremos de novo aqui, na
    # mesma mensagem já baixada, pra pegar os bytes.
    for parte in email_alvo["mensagem"].walk():
        if parte.get_content_disposition() != "attachment":
            continue

        nome_bruto = parte.get_filename()

        if not nome_bruto:
            continue

        # Mesma sanitização usada na origem (_listar_nomes_anexos) —
        # nomes_para_salvar já vem sanitizado, então a comparação
        # dos dois lados precisa passar pelo mesmo tratamento.
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

        # Defesa extra: confirma que o caminho final realmente fica
        # dentro de PASTA_DOWNLOADS_EMAIL antes de escrever, mesmo já
        # tendo sanitizado o nome acima — nunca confia em uma única
        # camada de proteção contra um nome vindo de fora.
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


# Evita sobrescrever um arquivo já existente no destino — adiciona
# um sufixo de data/hora, e um contador extra se ainda assim colidir
# (dois anexos de mesmo nome baixados no mesmo segundo, por exemplo).
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
