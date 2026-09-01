# Cria um arquivo de texto simples por pedido de voz — só dentro de
# uma das pastas em config.pastas_permitidas(), nunca em qualquer
# outro lugar do disco. Nome e extensão são sempre saneados (nunca um
# caminho vindo direto da fala/do modelo é usado cru), e um arquivo
# já existente NUNCA é sobrescrito silenciosamente — ganha sufixo de
# data/hora, mesmo padrão já usado por
# jarvis/servicos/email/leitor.py e
# jarvis/servicos/visao/captura_tela.py.
import os
import re
import unicodedata
from datetime import datetime

from . import config

# Limite de caracteres do conteúdo — isto é pra criar um arquivo de
# texto simples ditado por voz, não gerar um documento extenso.
# Conteúdo maior é truncado (nunca rejeitado silenciosamente), com um
# aviso anexado na mensagem de retorno — mesma convenção de
# _LIMITE_CARACTERES_TEXTO em jarvis/pacotes/chat_jarvis.
LIMITE_CARACTERES_CONTEUDO = 5000

_EXTENSAO_PADRAO = "txt"


def _remover_acentos(texto):
    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )


# Nome de arquivo seguro: primeiro tira acento (senão "relatório"
# viraria "relat_rio" no passo seguinte), depois restringe aos mesmos
# caracteres seguros já usados em
# jarvis/servicos/email/leitor.py (_nome_arquivo_seguro) — nunca um
# caminho (barra, "..", letra de unidade) sobrevive a isso, porque o
# nome nunca é tratado como caminho, só como um único componente de
# arquivo.
def _nome_arquivo_seguro(nome):
    nome = os.path.basename(
        (nome or "").strip()
    )

    nome = _remover_acentos(nome)

    nome = re.sub(
        r"[^A-Za-z0-9._\- ]",
        "_",
        nome,
    )

    return nome.strip(" ._")


def _extensao_segura(extensao):
    extensao = re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(extensao or "").strip(),
    )

    extensao = extensao.lower()[:10]

    return extensao or _EXTENSAO_PADRAO


# Mesmo padrão de jarvis/servicos/email/leitor.py: sufixo de
# data/hora, com contador extra só no raro caso de colisão mesmo
# assim (duas criações no mesmo segundo).
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


# Resolve o nome de pasta falado (ex: "Downloads", "Área de
# Trabalho") contra config.pastas_permitidas() — nunca aceita um
# caminho arbitrário vindo da fala, só o nome de uma pasta já
# cadastrada na lista permitida. Retorna o Path resolvido, ou None se
# não encontrar correspondência.
def _resolver_pasta_falada(pasta_falada, permitidas):
    alvo = _remover_acentos(pasta_falada).strip().lower()

    for pasta in permitidas:
        if _remover_acentos(pasta.name).strip().lower() == alvo:
            return pasta

    for pasta in permitidas:
        nome_pasta = _remover_acentos(pasta.name).strip().lower()

        if alvo in nome_pasta or nome_pasta in alvo:
            return pasta

    return None


# Cria o arquivo. Retorna (sucesso: bool, mensagem: str) — nunca
# lança exceção, nunca sobrescreve um arquivo existente, e nunca
# escreve fora de config.pastas_permitidas().
def criar_arquivo(nome, conteudo, pasta_falada=None, extensao="txt"):
    nome_seguro = _nome_arquivo_seguro(nome)

    if not nome_seguro:
        return False, (
            "Nome de arquivo inválido — não sobrou nada depois de "
            "remover caracteres não permitidos."
        )

    permitidas = config.pastas_permitidas()

    if pasta_falada:
        pasta_destino = _resolver_pasta_falada(pasta_falada, permitidas)

        if pasta_destino is None:
            nomes_permitidos = ", ".join(p.name for p in permitidas)

            return False, (
                f"'{pasta_falada}' não é uma pasta permitida pra criar "
                f"arquivo. Pastas permitidas: {nomes_permitidos}."
            )

    else:
        pasta_destino = config.pasta_padrao()

    pasta_destino_resolvida = pasta_destino.resolve()

    # Checagem final e definitiva: o destino PRECISA estar dentro de
    # uma pasta permitida, sem exceção — mesmo princípio de
    # jarvis/servicos/email/leitor.py (caminho resolvido precisa
    # bater com a pasta base, checado bem antes de qualquer escrita).
    permitido = any(
        pasta_destino_resolvida == pasta.resolve()
        for pasta in permitidas
    )

    if not permitido:
        return False, (
            f"'{pasta_destino}' não está entre as pastas permitidas "
            "pra criar arquivo."
        )

    extensao_segura = _extensao_segura(extensao)

    conteudo = conteudo or ""
    truncado = False

    if len(conteudo) > LIMITE_CARACTERES_CONTEUDO:
        conteudo = conteudo[:LIMITE_CARACTERES_CONTEUDO]
        truncado = True

    caminho_arquivo = (
        pasta_destino_resolvida / f"{nome_seguro}.{extensao_segura}"
    )

    # Defesa extra: confirma que o caminho final realmente fica
    # dentro da pasta de destino antes de escrever, mesmo já tendo
    # saneado o nome acima — nunca confia numa única camada de
    # proteção contra um nome vindo de fora (mesmo padrão de
    # jarvis/servicos/email/leitor.py:baixar_anexo).
    if pasta_destino_resolvida not in caminho_arquivo.resolve().parents:
        return False, "Caminho de destino inválido."

    caminho_final = _caminho_sem_sobrescrever(caminho_arquivo)

    try:
        caminho_final.write_text(conteudo, encoding="utf-8")

    except OSError as erro:
        return False, f"Falha ao criar o arquivo: {erro}"

    mensagem = (
        f"Arquivo '{caminho_final.name}' criado em "
        f"{pasta_destino_resolvida}."
    )

    if truncado:
        mensagem += (
            f" (conteúdo truncado em {LIMITE_CARACTERES_CONTEUDO} "
            "caracteres)"
        )

    return True, mensagem
