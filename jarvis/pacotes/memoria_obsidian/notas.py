# Camada de baixo nível do vault: ler, escrever e localizar notas .md.
# Tudo que escritor/busca/esquecer/consolidacao fazem passa por aqui,
# para as regras de segurança existirem em UM lugar só.
#
# Formato de uma nota:
#
#     ---
#     created: 2026-09-01T10:00:00
#     last_used: 2026-09-01T10:00:00
#     access_count: 0
#     pinned: false
#     ---
#
#     <conteúdo>
#
#     ## Relacionados
#     - [[Outra Nota]]
#
# O frontmatter é lido e escrito à mão, sem biblioteca de YAML: são só
# quatro campos escalares, e adicionar uma dependência nova ao projeto
# por causa disso não se justifica.
import difflib
import json
import os
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config

# Protege leitura e escrita concorrente das notas — o mesmo cuidado
# que jarvis/servicos/memoria/gerenciador.py já tinha, mantido aqui.
_LOCK = threading.RLock()

_DELIMITADOR = "---"
_TITULO_SECAO_RELACIONADOS = "## Relacionados"

# Caracteres proibidos em nome de arquivo no Windows, mais os que
# atrapalham o Obsidian dentro de um link [[...]].
_CARACTERES_PROIBIDOS = r'[<>:"/\\|?*\[\]#^]'


# Palavras que não distinguem uma nota da outra. Usadas tanto pela
# busca quanto pela detecção automática de links, para nenhuma das
# duas achar que "de", "para" ou "o que" significam alguma coisa.
IRRELEVANTES = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "para", "pra", "com", "sem", "sobre", "e", "ou", "que",
    "meu", "minha", "meus", "minhas", "seu", "sua", "eu", "voce",
    "qual", "quais", "quem", "onde", "quando", "como", "ao", "aos",
    "esse", "essa", "isso", "este", "esta", "isto", "ele", "ela",
    "sao", "foi", "ser", "ter", "tem", "mais", "muito", "tambem",
}


# Normalização usada em toda comparação de título: sem acento, em
# minúsculas, sem espaço duplicado. Mesma técnica já validada em
# jarvis/servicos/memoria/gerenciador.py, fechar_app/processos.py e
# discord_jarvis/contatos.py — cópia própria de propósito, seguindo a
# convenção do projeto de cada pacote não depender do interno de
# outro (aquelas funções são privadas dos pacotes delas).
def normalizar(texto):
    texto = str(texto or "").strip().lower()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    return re.sub(r"\s+", " ", texto).strip()


# Transforma um título em nome de arquivo válido.
#
# O título vem do usuário ou do modelo, ou seja, é entrada não
# confiável: sem isto, um título como "../../.env" escreveria fora do
# vault. Mesmo cuidado já aplicado aos nomes de anexo de email em
# jarvis/servicos/email/leitor.py. A checagem final de contenção fica
# em caminho_seguro(), que é a garantia de verdade — esta função é a
# primeira camada.
def nome_arquivo_do_titulo(titulo):
    base = os.path.basename(str(titulo or "").strip())

    base = re.sub(_CARACTERES_PROIBIDOS, "", base)
    base = re.sub(r"\s+", " ", base).strip(" .")

    if not base:
        base = "nota-sem-titulo"

    return base[:120] + ".md"


# Garante que um caminho está DENTRO da pasta permitida. É a regra
# central do pacote: o jarvis nunca escreve fora de
# PASTA_VAULT_JARVIS. Levanta ValueError se escapar — nunca devolve um
# caminho de fora "só avisando".
def caminho_seguro(caminho, pasta_base=None):
    if pasta_base is None:
        pasta_base = config.PASTA_VAULT

    if pasta_base is None:
        raise ValueError(
            "PASTA_VAULT_JARVIS não está configurada no .env."
        )

    base = Path(pasta_base).resolve()
    alvo = Path(caminho).resolve()

    if base != alvo and base not in alvo.parents:
        raise ValueError(
            f"Caminho fora da pasta permitida do vault: {alvo}"
        )

    return alvo


def garantir_pastas():
    if config.PASTA_VAULT is None:
        return False

    config.PASTA_VAULT.mkdir(parents=True, exist_ok=True)
    config.pasta_arquivo().mkdir(parents=True, exist_ok=True)

    return True


def agora():
    return datetime.now().isoformat(timespec="seconds")


# --- Frontmatter -----------------------------------------------------

def _converter_valor(bruto):
    bruto = bruto.strip()

    if bruto.lower() in ("true", "false"):
        return bruto.lower() == "true"

    if re.fullmatch(r"-?\d+", bruto):
        return int(bruto)

    return bruto


def _formatar_valor(valor):
    if isinstance(valor, bool):
        return "true" if valor else "false"

    return str(valor)


# Devolve (frontmatter_dict, corpo_texto). Uma nota sem frontmatter
# (por exemplo criada à mão no Obsidian) não é erro: recebe valores
# padrão, para o jarvis conseguir usá-la mesmo assim.
def separar_nota(texto):
    linhas = texto.split("\n")

    if not linhas or linhas[0].strip() != _DELIMITADOR:
        return _frontmatter_padrao(), texto.strip()

    fim = None

    for indice in range(1, len(linhas)):
        if linhas[indice].strip() == _DELIMITADOR:
            fim = indice
            break

    if fim is None:
        return _frontmatter_padrao(), texto.strip()

    frontmatter = _frontmatter_padrao()

    for linha in linhas[1:fim]:
        if ":" not in linha:
            continue

        chave, _, valor = linha.partition(":")
        frontmatter[chave.strip()] = _converter_valor(valor)

    corpo = "\n".join(linhas[fim + 1:]).strip()

    return frontmatter, corpo


def _frontmatter_padrao():
    momento = agora()

    return {
        "created": momento,
        "last_used": momento,
        "access_count": 0,
        "pinned": False,
    }


def montar_nota(frontmatter, corpo):
    linhas = [_DELIMITADOR]

    # Ordem fixa para o arquivo ficar estável entre gravações (evita
    # diff sujo se o vault estiver num repositório).
    for chave in ("created", "last_used", "access_count", "pinned"):
        if chave in frontmatter:
            linhas.append(
                f"{chave}: {_formatar_valor(frontmatter[chave])}"
            )

    for chave, valor in frontmatter.items():
        if chave not in ("created", "last_used", "access_count", "pinned"):
            linhas.append(f"{chave}: {_formatar_valor(valor)}")

    linhas.append(_DELIMITADOR)
    linhas.append("")
    linhas.append(corpo.strip())
    linhas.append("")

    return "\n".join(linhas)


# --- Leitura e escrita -----------------------------------------------

# Escrita atômica: grava em .tmp e substitui. Mesma técnica de
# jarvis/servicos/memoria/gerenciador.py — uma queda de energia no meio
# da gravação nunca deixa uma nota pela metade.
def escrever_nota(caminho, frontmatter, corpo):
    with _LOCK:
        destino = caminho_seguro(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)

        temporario = destino.with_suffix(".md.tmp")

        temporario.write_text(
            montar_nota(frontmatter, corpo),
            encoding="utf-8",
        )

        temporario.replace(destino)

    return destino


def ler_nota(caminho):
    with _LOCK:
        alvo = caminho_seguro(caminho)

        if not alvo.is_file():
            return None

        frontmatter, corpo = separar_nota(
            alvo.read_text(encoding="utf-8")
        )

    return {
        "titulo": alvo.stem,
        "caminho": alvo,
        "frontmatter": frontmatter,
        "corpo": corpo,
        "arquivada": alvo.parent.name == config.NOME_PASTA_ARQUIVO,
    }


# Lista as notas de uma pasta. Por padrão a pasta ATIVA do vault, sem
# descer na subpasta arquivo/ — busca e poda só enxergam o que está
# ativo.
def listar_notas(pasta=None, incluir_arquivo=False):
    if config.PASTA_VAULT is None:
        return []

    if pasta is None:
        pasta = (
            config.pasta_arquivo()
            if incluir_arquivo
            else config.PASTA_VAULT
        )

    if not Path(pasta).is_dir():
        return []

    notas = []

    for caminho in sorted(Path(pasta).glob("*.md")):
        nota = ler_nota(caminho)

        if nota:
            notas.append(nota)

    return notas


# --- Localização por título ------------------------------------------

# Encontra notas cujo título "casa" com o procurado, na mesma escada
# já usada em fechar_app/processos.py: exato, depois substring nos
# dois sentidos, depois difflib. Devolve SEMPRE uma lista — quem chama
# decide o que fazer com zero, um ou vários resultados. Nunca escolhe
# sozinho quando há ambiguidade.
def localizar_por_titulo(titulo, incluir_arquivo=False):
    alvo = normalizar(titulo)

    if not alvo:
        return []

    candidatas = listar_notas()

    if incluir_arquivo:
        candidatas += listar_notas(incluir_arquivo=True)

    exatas = [
        nota for nota in candidatas
        if normalizar(nota["titulo"]) == alvo
    ]

    if exatas:
        return exatas

    parciais = [
        nota for nota in candidatas
        if alvo in normalizar(nota["titulo"])
        or normalizar(nota["titulo"]) in alvo
    ]

    if parciais:
        return parciais

    mapa = {normalizar(n["titulo"]): n for n in candidatas}

    proximos = difflib.get_close_matches(
        alvo,
        list(mapa.keys()),
        n=5,
        cutoff=config.CORTE_TITULO_APROXIMADO,
    )

    return [mapa[chave] for chave in proximos]


# --- Links -----------------------------------------------------------

def extrair_links(corpo):
    return [
        alvo.strip()
        for alvo in re.findall(r"\[\[([^\]]+)\]\]", corpo or "")
        if alvo.strip()
    ]


# Reescreve a seção "## Relacionados" do corpo com os títulos dados.
# Preserva o texto acima dela; sem títulos, a seção some.
def aplicar_relacionados(corpo, titulos):
    corpo = (corpo or "").strip()

    posicao = corpo.find(_TITULO_SECAO_RELACIONADOS)

    if posicao != -1:
        corpo = corpo[:posicao].strip()

    unicos = []
    vistos = set()

    for titulo in titulos:
        chave = normalizar(titulo)

        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(str(titulo).strip())

    if not unicos:
        return corpo

    linhas = [corpo, "", _TITULO_SECAO_RELACIONADOS]

    for titulo in unicos:
        linhas.append(f"- [[{titulo}]]")

    return "\n".join(linhas).strip()


# --- Registro de uso -------------------------------------------------

# Marca a nota como usada AGORA: last_used vira a data atual e
# access_count sobe. É o que tira uma nota do caminho de poda.
def registrar_uso(caminho):
    with _LOCK:
        nota = ler_nota(caminho)

        if nota is None:
            return False

        frontmatter = nota["frontmatter"]
        frontmatter["last_used"] = agora()

        try:
            atual = int(frontmatter.get("access_count", 0))

        except (TypeError, ValueError):
            atual = 0

        frontmatter["access_count"] = atual + 1

        escrever_nota(nota["caminho"], frontmatter, nota["corpo"])

    return True


# --- Arquivo de controle da varredura --------------------------------

def ler_controle():
    caminho = config.ARQUIVO_CONTROLE

    if not caminho.is_file():
        return {}

    try:
        return json.loads(caminho.read_text(encoding="utf-8"))

    except (json.JSONDecodeError, OSError):
        return {}


def escrever_controle(dados):
    caminho = config.ARQUIVO_CONTROLE
    temporario = caminho.with_suffix(".json.tmp")

    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    temporario.replace(caminho)
