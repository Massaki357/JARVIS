import json
import re
import unicodedata

from datetime import datetime
from jarvis.caminhos import PASTA_DADOS, garantir_pasta
from threading import Lock


PASTA_MEMORIA = garantir_pasta(PASTA_DADOS)
ARQUIVO_MEMORIA = PASTA_MEMORIA / "memoria.json"

MAXIMO_MEMORIAS = 50
MAXIMO_CARACTERES = 200

_LOCK = Lock()


def _normalizar_texto(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def _criar_arquivo_se_necessario():
    PASTA_MEMORIA.mkdir(
        parents=True,
        exist_ok=True
    )

    if not ARQUIVO_MEMORIA.exists():
        _salvar_dados(
            {
                "versao": 1,
                "memorias": [],
            }
        )


def _carregar_dados():
    _criar_arquivo_se_necessario()

    try:
        with ARQUIVO_MEMORIA.open(
            "r",
            encoding="utf-8"
        ) as arquivo:
            dados = json.load(
                arquivo
            )

    except (
        json.JSONDecodeError,
        OSError,
    ):
        dados = {
            "versao": 1,
            "memorias": [],
        }

    if not isinstance(dados, dict):
        dados = {
            "versao": 1,
            "memorias": [],
        }

    memorias = dados.get(
        "memorias",
        []
    )

    if not isinstance(memorias, list):
        memorias = []

    memorias_validas = []

    for memoria in memorias:
        if not isinstance(memoria, dict):
            continue

        texto = str(
            memoria.get(
                "texto",
                ""
            )
        ).strip()

        if not texto:
            continue

        memorias_validas.append(
            {
                "id": str(
                    memoria.get(
                        "id",
                        ""
                    )
                ),
                "texto": texto,
                "criada_em": str(
                    memoria.get(
                        "criada_em",
                        ""
                    )
                ),
            }
        )

    return {
        "versao": 1,
        "memorias": memorias_validas,
    }


def _salvar_dados(dados):
    PASTA_MEMORIA.mkdir(
        parents=True,
        exist_ok=True
    )

    temporario = ARQUIVO_MEMORIA.with_suffix(
        ".tmp"
    )

    with temporario.open(
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    temporario.replace(
        ARQUIVO_MEMORIA
    )


def salvar_memoria(texto):
    if not isinstance(texto, str):
        return (
            "A memória informada é inválida."
        )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    ).strip()

    if not texto:
        return (
            "Não recebi nenhuma informação "
            "para memorizar."
        )

    if len(texto) > MAXIMO_CARACTERES:
        return (
            "Essa memória é longa demais. "
            f"Resuma em até {MAXIMO_CARACTERES} caracteres."
        )

    texto_normalizado = _normalizar_texto(
        texto
    )

    with _LOCK:
        dados = _carregar_dados()

        memorias = dados[
            "memorias"
        ]

        for memoria in memorias:
            memoria_normalizada = _normalizar_texto(
                memoria["texto"]
            )

            if memoria_normalizada == texto_normalizado:
                return (
                    "Essa informação já está "
                    "salva na memória."
                )

        if len(memorias) >= MAXIMO_MEMORIAS:
            return (
                "Minha memória persistente atingiu "
                f"o limite de {MAXIMO_MEMORIAS} informações. "
                "Peça para eu listar ou esquecer alguma "
                "memória antes de salvar outra."
            )

        proximo_id = 1

        ids_validos = []

        for memoria in memorias:
            try:
                ids_validos.append(
                    int(
                        memoria["id"]
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        if ids_validos:
            proximo_id = (
                max(ids_validos) + 1
            )

        memorias.append(
            {
                "id": str(
                    proximo_id
                ),
                "texto": texto,
                "criada_em": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }
        )

        dados["memorias"] = memorias

        _salvar_dados(
            dados
        )

    quantidade = len(
        memorias
    )

    restantes = (
        MAXIMO_MEMORIAS
        - quantidade
    )

    return (
        f"Memória salva: {texto}. "
        f"Tenho {quantidade} de "
        f"{MAXIMO_MEMORIAS} memórias ocupadas "
        f"e {restantes} disponíveis."
    )


def listar_memorias():
    with _LOCK:
        dados = _carregar_dados()

        memorias = dados[
            "memorias"
        ]

    if not memorias:
        return (
            "Nenhuma memória foi salva ainda."
        )

    linhas = []

    for memoria in memorias:
        linhas.append(
            f"{memoria['id']}. "
            f"{memoria['texto']}"
        )

    quantidade = len(
        memorias
    )

    return (
        f"Tenho {quantidade} de "
        f"{MAXIMO_MEMORIAS} memórias salvas:\n"
        + "\n".join(linhas)
    )


def esquecer_memoria(referencia):
    if not isinstance(referencia, str):
        return (
            "A referência da memória é inválida."
        )

    referencia = referencia.strip()

    if not referencia:
        return (
            "Informe qual memória deve "
            "ser esquecida."
        )

    referencia_normalizada = _normalizar_texto(
        referencia
    )

    comandos_apagar_tudo = {
        "tudo",
        "todas",
        "todas as memorias",
        "apagar tudo",
        "limpar tudo",
        "esquecer tudo",
    }

    if referencia_normalizada in comandos_apagar_tudo:
        return (
            "Por segurança, não apago todas "
            "as memórias em uma única solicitação. "
            "Peça para esquecer uma informação específica."
        )

    with _LOCK:
        dados = _carregar_dados()

        memorias = dados[
            "memorias"
        ]

        encontrada = None

        for memoria in memorias:
            if memoria["id"] == referencia:
                encontrada = memoria
                break

        if encontrada is None:
            for memoria in memorias:
                texto_normalizado = _normalizar_texto(
                    memoria["texto"]
                )

                if (
                    texto_normalizado
                    == referencia_normalizada
                ):
                    encontrada = memoria
                    break

        if encontrada is None:
            candidatas = []

            for memoria in memorias:
                texto_normalizado = _normalizar_texto(
                    memoria["texto"]
                )

                if (
                    referencia_normalizada
                    in texto_normalizado
                ):
                    candidatas.append(
                        memoria
                    )

            if len(candidatas) == 1:
                encontrada = candidatas[
                    0
                ]

            elif len(candidatas) > 1:
                opcoes = ", ".join(
                    (
                        f"{memoria['id']}: "
                        f"{memoria['texto']}"
                    )
                    for memoria
                    in candidatas[:5]
                )

                return (
                    "Encontrei mais de uma "
                    "memória parecida. "
                    "Peça para esquecer pelo número: "
                    + opcoes
                )

        if encontrada is None:
            return (
                "Não encontrei uma memória "
                "correspondente."
            )

        memorias.remove(
            encontrada
        )

        dados["memorias"] = memorias

        _salvar_dados(
            dados
        )

        quantidade = len(
            memorias
        )

    return (
        "Memória esquecida: "
        f"{encontrada['texto']}. "
        f"Agora tenho {quantidade} de "
        f"{MAXIMO_MEMORIAS} memórias ocupadas."
    )


def contexto_memorias():
    with _LOCK:
        dados = _carregar_dados()

        memorias = dados[
            "memorias"
        ]

    if not memorias:
        return (
            "MEMÓRIA PERSISTENTE:\n"
            "Nenhuma memória salva."
        )

    linhas = [
        f"- {memoria['texto']}"
        for memoria in memorias
    ]

    return (
        "MEMÓRIA PERSISTENTE DO USUÁRIO:\n"
        + "\n".join(linhas)
        + "\nUse essas informações somente quando "
        "forem relevantes para o pedido atual. "
        "Não mencione a existência deste bloco "
        "sem necessidade."
    )
