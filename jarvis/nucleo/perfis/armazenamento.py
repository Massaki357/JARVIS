import json
import os
import re
import shutil
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from jarvis.caminhos import PASTA_PERFIS, garantir_pasta

from . import catalogo_ferramentas
from . import ferramentas_diretas

_LOCK = threading.RLock()

ARQUIVO_PERFIL = "perfil.json"
ARQUIVO_SISTEMA = "sistema.md"

ARQUIVO_INDICE = "indice.json"

SLUG_PADRAO = "completo"
NOME_PADRAO = "jarvis completo"

CHAVE_PERFIL_ATIVO = "perfil_ativo"

TODAS_AS_FERRAMENTAS = None

_SLUGS_RESERVADOS = {"indice"}

_CARACTERES_SLUG = re.compile(r"[^a-z0-9-]+")


def gerar_slug(nome):
    base = os.path.basename(str(nome or "").strip())

    base = unicodedata.normalize("NFD", base)

    base = "".join(
        caractere
        for caractere in base
        if unicodedata.category(caractere) != "Mn"
    )

    base = _CARACTERES_SLUG.sub("-", base.lower()).strip("-")
    base = re.sub(r"-{2,}", "-", base)

    if not base or base in _SLUGS_RESERVADOS:
        base = "perfil"

    return base[:60]


def slug_disponivel(slug_base):
    slug = gerar_slug(slug_base)

    if not caminho_do_perfil(slug).exists():
        return slug

    contador = 2

    while caminho_do_perfil(f"{slug}-{contador}").exists():
        contador += 1

    return f"{slug}-{contador}"


def caminho_do_perfil(slug):
    limpo = str(slug or "").strip()

    if not limpo:
        raise ValueError("Slug de perfil vazio.")

    base = Path(PASTA_PERFIS).resolve()
    alvo = (base / limpo).resolve()

    if alvo.parent != base:
        raise ValueError(
            f"Slug de perfil inválido (sairia de dados/perfis/): {slug!r}"
        )

    if alvo.name in _SLUGS_RESERVADOS:
        raise ValueError(
            f"Slug de perfil reservado: {alvo.name!r}"
        )

    return alvo


def caminho_do_indice():
    return Path(PASTA_PERFIS) / ARQUIVO_INDICE


def _escrever_texto(caminho, texto):
    caminho = Path(caminho)

    garantir_pasta(caminho.parent)

    temporario = caminho.with_name(caminho.name + ".tmp")

    temporario.write_text(texto, encoding="utf-8")
    temporario.replace(caminho)


def _escrever_json(caminho, dados):
    _escrever_texto(
        caminho,
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
    )


def normalizar_ferramentas(ferramentas, validar=True):
    if ferramentas is TODAS_AS_FERRAMENTAS:
        return TODAS_AS_FERRAMENTAS

    pedidas = [
        str(nome).strip()
        for nome in ferramentas
        if str(nome).strip()
    ]

    if validar:
        disponiveis = catalogo_ferramentas.nomes_disponiveis()
        inexistentes = [
            nome for nome in pedidas if nome not in disponiveis
        ]

        if inexistentes:
            raise ValueError(
                "Ferramenta inexistente no projeto: "
                f"{sorted(set(inexistentes))}"
            )

    resultado = []

    for nome in pedidas:
        if nome not in resultado:
            resultado.append(nome)

    for nome in catalogo_ferramentas.FERRAMENTAS_SEMPRE_ATIVAS:
        if nome not in resultado:
            resultado.append(nome)

    return resultado


# Perfil padrão é imutável: editar_perfil levanta em vez de ignorar (docs/perfis.md).
def ferramentas_editaveis(perfil):
    if not isinstance(perfil, dict):
        perfil = carregar_perfil(perfil)

    return not perfil["padrao"]


def ferramentas_efetivas(perfil):
    if not isinstance(perfil, dict):
        perfil = carregar_perfil(perfil)

    if perfil["ferramentas"] is TODAS_AS_FERRAMENTAS:
        return sorted(catalogo_ferramentas.nomes_disponiveis())

    return list(perfil["ferramentas"])


# Não lê disco: a lista curta já foi carregada em preparar_chamada.
# O porte do modo local compete com a visão nativa e leva o modelo ao caminho lento, calado por segundos.
_PORTES_DA_VISAO_NATIVA = {
    "descrever_tela": "analisar_tela",
    "descrever_camera": "analisar_camera",
}


def filtrar_declaracoes(declaracoes, permitidas):
    if permitidas is None:
        filtradas = list(declaracoes)

    else:
        filtradas = [
            declaracao
            for declaracao in declaracoes
            if getattr(declaracao, "name", None) in permitidas
        ]

    nomes = {getattr(declaracao, "name", None) for declaracao in filtradas}

    filtradas = [
        declaracao
        for declaracao in filtradas
        if _PORTES_DA_VISAO_NATIVA.get(getattr(declaracao, "name", None))
        not in nomes
    ]

    return ferramentas_diretas.aplicar_descricoes_curtas(filtradas)


# Nunca levanta: se falhar, declara tudo (caro, mas funciona).
def _sem_as_ocultas(permitidas):
    from jarvis.nucleo.config import FERRAMENTAS_SOB_DEMANDA

    if not FERRAMENTAS_SOB_DEMANDA:
        return permitidas

    try:
        from jarvis.nucleo.registro_pacotes import ferramentas_ocultas

        ocultas = ferramentas_ocultas()

        if not ocultas:
            return permitidas

        if permitidas is None:
            permitidas = set(catalogo_ferramentas.nomes_disponiveis())

        return set(permitidas) - ocultas

    except Exception as erro:
        print(
            "[PERFIL] Não consegui resolver as ferramentas sob "
            f"demanda; declarando todas. ({erro})"
        )

        return permitidas


# FALHA FECHADA: perfil ilegível abre só com FERRAMENTAS_SEMPRE_ATIVAS (docs/perfis.md).
def preparar_chamada(slug=None):
    slug = slug or perfil_ativo()

    ferramentas_diretas.carregar_para_chamada(slug)

    try:
        perfil = carregar_perfil(slug)

        return {
            "slug": perfil["slug"],
            "permitidas": _sem_as_ocultas(
                None
                if perfil["ferramentas"] is TODAS_AS_FERRAMENTAS
                else set(perfil["ferramentas"])
            ),
            "prompt_bruto": perfil["prompt_sistema"],
            "aviso": "",
        }

    except (FileNotFoundError, ValueError, OSError, KeyError) as erro:
        print(
            f"[perfis] Perfil {slug!r} não pôde ser carregado ({erro}) "
            "— a chamada vai SEM ferramentas, por segurança."
        )

        return {
            "slug": slug,
            "permitidas": set(
                catalogo_ferramentas.FERRAMENTAS_SEMPRE_ATIVAS
            ),
            "prompt_bruto": _prompt_de_emergencia(),
            "aviso": (
                f"Não consegui carregar o perfil \"{slug}\". Por "
                "segurança, esta chamada está SEM ferramentas — só dá "
                "para conversar e encerrar. Confira a pasta "
                f"dados/perfis/{slug}/ e reinicie a chamada."
            ),
        }


def _prompt_de_emergencia():
    try:
        return carregar_perfil(SLUG_PADRAO)["prompt_sistema"]

    except (FileNotFoundError, ValueError, OSError, KeyError):
        return ""


def _ler_perfil_json(pasta):
    dados = json.loads(
        (pasta / ARQUIVO_PERFIL).read_text(encoding="utf-8")
    )

    if not isinstance(dados, dict):
        raise ValueError(
            f"{pasta.name}/{ARQUIVO_PERFIL} não é um objeto JSON."
        )

    return dados


def existe(slug):
    try:
        pasta = caminho_do_perfil(slug)

    except ValueError:
        return False

    return (pasta / ARQUIVO_PERFIL).is_file()


def carregar_perfil(slug):
    with _LOCK:
        pasta = caminho_do_perfil(slug)

        if not (pasta / ARQUIVO_PERFIL).is_file():
            raise FileNotFoundError(
                f"Perfil não encontrado: {slug!r}"
            )

        dados = _ler_perfil_json(pasta)

        arquivo_sistema = pasta / ARQUIVO_SISTEMA

        prompt = (
            arquivo_sistema.read_text(encoding="utf-8")
            if arquivo_sistema.is_file()
            else ""
        )

        ferramentas = dados.get("ferramentas", TODAS_AS_FERRAMENTAS)

        return {
            "slug": pasta.name,
            "nome": str(
                dados.get("nome") or pasta.name
            ).strip(),
            "descricao": str(dados.get("descricao") or ""),
            "ferramentas": (
                None
                if ferramentas is None
                else list(ferramentas)
            ),
            "padrao": bool(dados.get("padrao", False)),
            "criado_em": dados.get("criado_em", ""),
            "atualizado_em": dados.get("atualizado_em", ""),
            "prompt_sistema": prompt,
            "pasta": pasta,
        }


def texto_sistema(slug):
    return carregar_perfil(slug)["prompt_sistema"]


def listar_perfis():
    with _LOCK:
        caminho = caminho_do_indice()

        if not caminho.is_file():
            return reconstruir_indice()

        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            entradas = dados["perfis"]

            if not isinstance(entradas, list):
                raise ValueError("campo 'perfis' não é uma lista")

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            OSError,
        ) as erro:
            print(
                f"[perfis] indice.json ilegível ({erro}) — "
                "reconstruindo a partir das pastas."
            )
            return reconstruir_indice()

        slugs_indice = {
            entrada.get("slug")
            for entrada in entradas
            if isinstance(entrada, dict)
        }

        if slugs_indice != set(_slugs_em_disco()):
            print(
                "[perfis] indice.json divergindo das pastas — "
                "reconstruindo."
            )
            return reconstruir_indice()

        return [
            {
                "slug": entrada["slug"],
                "nome": entrada.get("nome", entrada["slug"]),
                "padrao": bool(entrada.get("padrao", False)),
            }
            for entrada in entradas
            if isinstance(entrada, dict) and entrada.get("slug")
        ]


def _slugs_em_disco():
    pasta_base = Path(PASTA_PERFIS)

    if not pasta_base.is_dir():
        return []

    return sorted(
        item.name
        for item in pasta_base.iterdir()
        if item.is_dir() and (item / ARQUIVO_PERFIL).is_file()
    )


def reconstruir_indice():
    with _LOCK:
        entradas = []

        for slug in _slugs_em_disco():
            pasta = caminho_do_perfil(slug)

            try:
                dados = _ler_perfil_json(pasta)

            except (json.JSONDecodeError, ValueError, OSError) as erro:
                print(
                    f"[perfis] Pasta {slug!r} com {ARQUIVO_PERFIL} "
                    f"ilegível ({erro}) — fora do índice."
                )
                continue

            entradas.append(
                {
                    "slug": slug,
                    "nome": str(dados.get("nome") or slug).strip(),
                    "padrao": bool(dados.get("padrao", False)),
                }
            )

        entradas.sort(
            key=lambda entrada: (
                not entrada["padrao"],
                entrada["nome"].lower(),
            )
        )

        _escrever_json(
            caminho_do_indice(),
            {
                "comentario": (
                    "Índice DERIVADO das pastas de dados/perfis/. "
                    "Não edite à mão: é regravado a cada criação, "
                    "edição ou exclusão de perfil. A fonte da verdade "
                    "é a pasta de cada perfil."
                ),
                "gerado_em": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "perfis": entradas,
            },
        )

        return entradas


def criar_perfil(
    nome,
    prompt_sistema,
    ferramentas=TODAS_AS_FERRAMENTAS,
    descricao="",
    slug=None,
    padrao=False,
    validar_ferramentas=True,
):
    with _LOCK:
        nome = str(nome or "").strip()

        if not nome:
            raise ValueError("O perfil precisa de um nome.")

        slug = (
            gerar_slug(slug)
            if slug
            else slug_disponivel(nome)
        )

        pasta = caminho_do_perfil(slug)

        if existe(slug):
            raise ValueError(
                f"Já existe um perfil com o slug {slug!r}."
            )

        ferramentas = normalizar_ferramentas(
            ferramentas,
            validar=validar_ferramentas,
        )

        agora = datetime.now().isoformat(timespec="seconds")

        garantir_pasta(pasta)

        _escrever_json(
            pasta / ARQUIVO_PERFIL,
            {
                "slug": slug,
                "nome": nome,
                "descricao": str(descricao or ""),
                "ferramentas": ferramentas,
                "padrao": bool(padrao),
                "criado_em": agora,
                "atualizado_em": agora,
            },
        )

        _escrever_texto(
            pasta / ARQUIVO_SISTEMA,
            str(prompt_sistema or ""),
        )

        reconstruir_indice()

        return carregar_perfil(slug)


_NAO_INFORMADO = object()


def editar_perfil(
    slug,
    nome=None,
    prompt_sistema=None,
    ferramentas=_NAO_INFORMADO,
    descricao=None,
    validar_ferramentas=True,
):
    with _LOCK:
        atual = carregar_perfil(slug)
        pasta = atual["pasta"]

        if nome is not None:
            nome = str(nome).strip()

            if not nome:
                raise ValueError("O nome do perfil não pode ficar vazio.")

        if ferramentas is _NAO_INFORMADO:
            ferramentas = atual["ferramentas"]

        ferramentas = normalizar_ferramentas(
            ferramentas,
            validar=validar_ferramentas,
        )

        if not ferramentas_editaveis(atual):
            if ferramentas is not TODAS_AS_FERRAMENTAS:
                raise ValueError(
                    "A lista de ferramentas do perfil padrão não pode "
                    "ser alterada: ele representa o jarvis completo e "
                    "precisa continuar valendo para TODAS as "
                    "ferramentas registradas, inclusive as que forem "
                    "adicionadas ao projeto depois. Para um "
                    "subconjunto, crie um perfil novo."
                )

        _escrever_json(
            pasta / ARQUIVO_PERFIL,
            {
                "slug": atual["slug"],
                "nome": nome if nome is not None else atual["nome"],
                "descricao": (
                    str(descricao)
                    if descricao is not None
                    else atual["descricao"]
                ),
                "ferramentas": ferramentas,
                "padrao": atual["padrao"],
                "criado_em": atual["criado_em"],
                "atualizado_em": datetime.now().isoformat(
                    timespec="seconds"
                ),
            },
        )

        if prompt_sistema is not None:
            _escrever_texto(
                pasta / ARQUIVO_SISTEMA,
                str(prompt_sistema),
            )

        reconstruir_indice()

        return carregar_perfil(atual["slug"])


def apagar_perfil(slug):
    with _LOCK:
        perfil = carregar_perfil(slug)

        if perfil["padrao"]:
            raise ValueError(
                "O perfil padrão não pode ser apagado."
            )

        pasta = perfil["pasta"]

        if not (pasta / ARQUIVO_PERFIL).is_file():
            raise ValueError(
                f"{pasta} não parece uma pasta de perfil — nada apagado."
            )

        shutil.rmtree(pasta)

        if perfil_ativo_bruto() == perfil["slug"]:
            definir_perfil_ativo(SLUG_PADRAO)

        reconstruir_indice()

        return True


def perfil_ativo_bruto():
    from jarvis.nucleo import preferencias

    return str(
        preferencias.ler_preferencia(CHAVE_PERFIL_ATIVO, "") or ""
    ).strip()


def perfil_ativo():
    slug = perfil_ativo_bruto()

    if slug and existe(slug):
        return slug

    return SLUG_PADRAO


def definir_perfil_ativo(slug):
    from jarvis.nucleo import preferencias

    if slug and not existe(slug):
        raise FileNotFoundError(f"Perfil não encontrado: {slug!r}")

    return preferencias.salvar_preferencia(
        CHAVE_PERFIL_ATIVO,
        str(slug or ""),
    )
