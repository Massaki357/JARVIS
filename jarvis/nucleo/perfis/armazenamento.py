# Camada de dados dos perfis: ler e escrever perfis em disco, sem
# nenhuma dependência de interface. Tudo que a Fase 2 (janela) e a
# Fase 5 (início da chamada) vão precisar passa por aqui.
#
# Layout em disco
# ===============
#
#     dados/perfis/
#       indice.json              <- índice leve, DERIVADO (nunca à mão)
#       completo/                <- um perfil = uma pasta autocontida
#         perfil.json
#         sistema.md
#       consultor-investimentos/
#         perfil.json
#         sistema.md
#
# A PASTA é a fonte da verdade. O indice.json existe só para o select
# da interface abrir instantaneamente sem ter que ler N pastas, e é
# regravado a cada criação, edição e exclusão. Se ele sumir, ficar
# corrompido ou divergir, reconstruir_indice() varre as pastas e o
# refaz — o índice nunca é a única cópia de nada.
#
# Por que dois arquivos por perfil, e não um só
# ============================================
#
# - perfil.json: os dados estruturados (nome de exibição, lista de
#   ferramentas, metadados). JSON porque é lido por código, e escrito
#   de uma vez só, atomicamente.
# - sistema.md: o prompt de sistema, no MESMO formato do
#   gemini_live_sistema.md que ele substitui — linhas de texto com
#   cabeçalhos "##" que servem só de navegação humana e são
#   descartados na hora de montar o texto enviado ao modelo (ver
#   jarvis/nucleo/prompts/__init__.py::_montar_texto). Ele fica fora
#   do JSON de propósito: um prompt de 22 mil caracteres espremido
#   numa string JSON de uma linha só é ilegível num diff, que é
#   exatamente o motivo pelo qual ele já tinha virado .md antes deste
#   sistema de perfis existir.
#
# Onde o código mora vs. onde os dados moram
# ==========================================
#
# Este módulo (código) fica em jarvis/nucleo/perfis/; os perfis
# (dados) ficam em dados/perfis/. Separados porque um slug de perfil
# é texto vindo do usuário e do modelo: se as duas coisas
# dividissem a mesma pasta, um perfil chamado "armazenamento" viraria
# uma pasta com o mesmo nome de um módulo Python ao lado. Assim,
# dados/perfis/ contém só perfil, e nenhum nome de slug pode colidir
# com nada.
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

# Protege leitura e escrita concorrente dos perfis e do índice. A
# janela de perfis roda na thread da GUI e o início da chamada roda na
# thread do worker — as duas podem tocar nestes arquivos. Mesmo
# cuidado de jarvis/pacotes/memoria_obsidian/notas.py.
_LOCK = threading.RLock()

# Nome dos arquivos dentro da pasta de cada perfil.
ARQUIVO_PERFIL = "perfil.json"
ARQUIVO_SISTEMA = "sistema.md"

# Índice central, único arquivo fora das pastas de perfil.
ARQUIVO_INDICE = "indice.json"

# Slug do perfil padrão — o jarvis completo, com todas as ferramentas
# e o prompt que o projeto sempre usou. É uma entrada normal da mesma
# estrutura (mesma pasta, mesmos dois arquivos), não um caso especial
# hardcoded: a única coisa que o distingue é o campo "padrao": true no
# perfil.json dele, que impede que ele seja apagado.
SLUG_PADRAO = "completo"
NOME_PADRAO = "jarvis completo"

# Chave em config.json (jarvis/nucleo/preferencias.py) com o slug do
# perfil escolhido para a PRÓXIMA chamada. Preferência local desta
# máquina, igual a microfone/alto_falante — por isso config.json, e
# não .env nem um arquivo novo.
CHAVE_PERFIL_ATIVO = "perfil_ativo"

# "ferramentas": null no perfil.json significa TODAS as ferramentas
# registradas, resolvidas na hora. Guardar a lista explícita das 61 no
# perfil padrão faria um pacote novo nascer desligado nele, em
# silêncio — o padrão precisa continuar significando "tudo o que o
# projeto tem hoje", não "tudo o que ele tinha no dia em que a pasta
# foi criada".
TODAS_AS_FERRAMENTAS = None

# Nome de pasta que um perfil nunca pode ter: colidiria com o índice.
_SLUGS_RESERVADOS = {"indice"}

_CARACTERES_SLUG = re.compile(r"[^a-z0-9-]+")


# ============================================================
# Slug e caminhos
# ============================================================

def gerar_slug(nome):
    """
    Transforma um nome de exibição em slug de pasta: sem acento, em
    minúsculas, só letras/números/hífen.

    O nome vem do usuário ou do modelo, ou seja, entrada não
    confiável: sem isto, um nome como "../../.env" viraria uma pasta
    fora de dados/perfis/. Esta é a primeira camada; a garantia de
    verdade é caminho_do_perfil(), que confere a contenção do caminho
    já resolvido. Mesma dupla de camadas usada em
    jarvis/pacotes/memoria_obsidian/notas.py e em
    jarvis/pacotes/criar_arquivo/escritor.py.
    """
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
    """
    Devolve o slug_base, ou slug_base-2, -3... até achar uma pasta que
    ainda não existe. Nunca sobrescreve um perfil existente só porque
    dois nomes de exibição geraram o mesmo slug.
    """
    slug = gerar_slug(slug_base)

    if not caminho_do_perfil(slug).exists():
        return slug

    contador = 2

    while caminho_do_perfil(f"{slug}-{contador}").exists():
        contador += 1

    return f"{slug}-{contador}"


def caminho_do_perfil(slug):
    """
    Caminho da pasta de um perfil, garantidamente DENTRO de
    dados/perfis/. Levanta ValueError se o slug tentar escapar —
    nunca devolve um caminho de fora "só avisando".
    """
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


# ============================================================
# Escrita atômica
# ============================================================

def _escrever_texto(caminho, texto):
    """
    Grava um arquivo de forma atômica (temporário + replace), mesma
    técnica de jarvis/nucleo/preferencias.py e de
    memoria_obsidian/notas.py: uma queda no meio da gravação não pode
    deixar um perfil.json pela metade e quebrar a listagem de perfis.
    """
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


# ============================================================
# Ferramentas de um perfil
# ============================================================

def normalizar_ferramentas(ferramentas, validar=True):
    """
    Normaliza a lista de ferramentas de um perfil.

    - None (TODAS_AS_FERRAMENTAS) passa direto: significa "todas as
      registradas", resolvido só na hora do uso.
    - Uma lista vira lista de strings sem repetição, na ordem em que
      foram informadas, com FERRAMENTAS_SEMPRE_ATIVAS garantidas no
      fim — um perfil não pode ficar sem como encerrar a chamada.
    - Com validar=True, um nome que não existe no catálogo é ERRO
      (ValueError), nunca é ignorado em silêncio. É a regra que a
      Fase 3 vai aplicar à resposta do cérebro.
    """
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


def ferramentas_editaveis(perfil):
    """
    Se a LISTA DE FERRAMENTAS deste perfil pode ser alterada.

    Falso só para o perfil padrão, e isso é um invariante do sistema,
    não uma preferência: o padrão é "o jarvis completo, todas as
    ferramentas", guardado como o curinga None (TODAS_AS_FERRAMENTAS)
    justamente para ser resolvido na hora do uso. Deixar editar essa
    lista congelaria o curinga numa lista fixa, e todo pacote
    adicionado ao projeto depois disso nasceria DESLIGADO no único
    perfil que deveria ter tudo — sem erro, sem aviso, só descoberto
    no dia em que alguém precisasse daquela ferramenta.

    Um aviso na tela não resolveria isso: depende de alguém ler e
    entender a implicação na hora certa. A trava, não.

    Quem quer um subconjunto parecido com o padrão tem a opção certa:
    criar um perfil novo. O resto dos metadados do padrão (nome de
    exibição, descrição, prompt) continua editável normalmente.

    Aceita o dict de carregar_perfil() ou o slug.
    """
    if not isinstance(perfil, dict):
        perfil = carregar_perfil(perfil)

    return not perfil["padrao"]


def ferramentas_efetivas(perfil):
    """
    Lista concreta de nomes de ferramenta de um perfil já carregado —
    com o None do perfil padrão resolvido para todas as ferramentas
    que existem AGORA.

    Aceita o dict devolvido por carregar_perfil() ou o slug.
    """
    if not isinstance(perfil, dict):
        perfil = carregar_perfil(perfil)

    if perfil["ferramentas"] is TODAS_AS_FERRAMENTAS:
        return sorted(catalogo_ferramentas.nomes_disponiveis())

    return list(perfil["ferramentas"])


# ============================================================
# Ler
# ============================================================

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
    """
    Carrega um perfil INTEIRO a partir da pasta dele: metadados,
    lista de ferramentas e o texto do prompt de sistema.

    Levanta FileNotFoundError se o perfil não existir. É a leitura da
    fonte da verdade — nunca usa o índice.
    """
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
    """
    Só o texto BRUTO do sistema.md de um perfil, do jeito que está no
    arquivo — com os cabeçalhos "##" e as quebras de linha. É isto
    que o QTextEdit da tela de edição mostra, e é a partir disto que
    jarvis/nucleo/prompts/ monta o texto final enviado ao modelo.
    """
    return carregar_perfil(slug)["prompt_sistema"]


def listar_perfis():
    """
    Lista leve para o select da interface: [{"slug", "nome",
    "padrao"}], lida do índice.

    Se o índice não existir, estiver corrompido ou não bater com as
    pastas que existem em disco, ele é reconstruído a partir das
    pastas antes de responder — o índice nunca é a única cópia da
    informação.
    """
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


# ============================================================
# Índice
# ============================================================

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
    """
    Varre dados/perfis/, lê o perfil.json de cada pasta e regrava o
    indice.json. Devolve a mesma lista leve de listar_perfis().

    Chamada automaticamente por toda operação de escrita e por
    listar_perfis() quando o índice não bate com o disco. O perfil
    padrão vem sempre primeiro; os demais em ordem alfabética de nome
    de exibição, que é a ordem em que aparecem no select.
    """
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


# ============================================================
# Escrever
# ============================================================

def criar_perfil(
    nome,
    prompt_sistema,
    ferramentas=TODAS_AS_FERRAMENTAS,
    descricao="",
    slug=None,
    padrao=False,
    validar_ferramentas=True,
):
    """
    Cria a pasta de um perfil novo com os dois arquivos preenchidos e
    atualiza o índice. Devolve o perfil carregado.

    O slug é derivado do nome (com sufixo numérico se já existir),
    a menos que um seja passado explicitamente. Levanta ValueError se
    o slug já existir ou se alguma ferramenta não existir no projeto.
    """
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

        # Checa o perfil.json, não a pasta: uma pasta que existe mas
        # ainda não tem perfil.json é justamente o caso da migração
        # do perfil padrão (o sistema.md chega primeiro, versionado no
        # repositório, e os metadados são criados aqui). Um perfil de
        # verdade — com perfil.json — nunca é sobrescrito.
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


# Sentinela para distinguir "não passou o argumento" de "passou None"
# — necessário porque None é um valor VÁLIDO de ferramentas (todas).
_NAO_INFORMADO = object()


def editar_perfil(
    slug,
    nome=None,
    prompt_sistema=None,
    ferramentas=_NAO_INFORMADO,
    descricao=None,
    validar_ferramentas=True,
):
    """
    Regrava os campos informados de um perfil existente e atualiza o
    índice. Campo não informado fica como está.

    Devolve o perfil recarregado. Levanta FileNotFoundError se o
    perfil não existir, ValueError se alguma ferramenta não existir.
    """
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

        # A LISTA DE FERRAMENTAS do perfil padrão é imutável — ver
        # ferramentas_editaveis() acima para o porquê. A trava mora
        # aqui, na camada de dados, e não só na tela: a tela desabilita
        # os botões para explicar ao usuário, mas quem GARANTE é isto,
        # que vale para qualquer chamador (a Fase 3, um script, um
        # teste). Levanta em vez de ignorar em silêncio: uma edição
        # aceita e não aplicada seria pior que uma recusa.
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
    """
    Apaga a pasta inteira de um perfil e atualiza o índice.

    Recusa apagar o perfil padrão: sem ele o app fica sem prompt de
    sistema nenhum para começar uma chamada. Também recusa apagar
    qualquer pasta que não tenha um perfil.json dentro — a exclusão
    passa por caminho_do_perfil() (contenção dentro de dados/perfis/)
    E por essa checagem, porque isto aqui é a única operação
    destrutiva do módulo.

    Se o perfil apagado era o ativo, a preferência volta para o
    padrão em vez de apontar para uma pasta que não existe mais.
    """
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


# ============================================================
# Perfil ativo (preferência local desta máquina)
# ============================================================

def perfil_ativo_bruto():
    """Slug guardado em config.json, sem validar se ainda existe."""
    from jarvis.nucleo import preferencias

    return str(
        preferencias.ler_preferencia(CHAVE_PERFIL_ATIVO, "") or ""
    ).strip()


def perfil_ativo():
    """
    Slug do perfil que vale para a PRÓXIMA chamada. Cai no padrão
    quando não há nada escolhido, ou quando o perfil escolhido foi
    apagado por fora.
    """
    slug = perfil_ativo_bruto()

    if slug and existe(slug):
        return slug

    return SLUG_PADRAO


def definir_perfil_ativo(slug):
    """
    Guarda o slug do perfil escolhido em config.json. Não afeta uma
    chamada em andamento — quem lê isso é o início da próxima
    (Fase 5).
    """
    from jarvis.nucleo import preferencias

    if slug and not existe(slug):
        raise FileNotFoundError(f"Perfil não encontrado: {slug!r}")

    return preferencias.salvar_preferencia(
        CHAVE_PERFIL_ATIVO,
        str(slug or ""),
    )
