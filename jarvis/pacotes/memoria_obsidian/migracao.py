import json
import sys
from datetime import datetime

from jarvis.caminhos import PASTA_DADOS

from . import config, notas

ARQUIVO_ANTIGO = PASTA_DADOS / "memoria.json"

MAXIMO_TITULO = 60


def _titulo_da_frase(texto):
    texto = " ".join(str(texto or "").split())

    if not texto:
        return "Memória sem título"

    for marca in (". ", "; ", " - "):
        posicao = texto.find(marca)

        if 0 < posicao <= MAXIMO_TITULO:
            return texto[:posicao].strip(" .;-")

    texto = texto.rstrip(" .")

    if len(texto) <= MAXIMO_TITULO:
        return texto

    corte = texto[:MAXIMO_TITULO].rsplit(" ", 1)[0]

    return corte.strip(" .,;") or texto[:MAXIMO_TITULO]


def _carregar_memorias_antigas():
    if not ARQUIVO_ANTIGO.is_file():
        return None, f"Arquivo não encontrado: {ARQUIVO_ANTIGO}"

    try:
        dados = json.loads(
            ARQUIVO_ANTIGO.read_text(encoding="utf-8")
        )

    except (json.JSONDecodeError, OSError) as erro:
        return None, f"Não consegui ler {ARQUIVO_ANTIGO}: {erro}"

    if isinstance(dados, dict):
        memorias = dados.get("memorias", [])

    elif isinstance(dados, list):
        memorias = dados

    else:
        return None, "Formato inesperado no arquivo de memórias."

    return memorias, ""


def migrar(confirmar=True):
    if not config.configurado():
        print(
            "PASTA_VAULT_JARVIS não está definida no .env. "
            "Defina o caminho da pasta do vault antes de migrar."
        )

        return False

    memorias, erro = _carregar_memorias_antigas()

    if memorias is None:
        print(erro)
        return False

    if not memorias:
        print("Não há memórias antigas para migrar.")
        return True

    print(
        f"Encontrei {len(memorias)} memória(s) em {ARQUIVO_ANTIGO}."
    )
    print(f"Elas serão criadas como notas .md em: {config.PASTA_VAULT}")
    print(
        "O arquivo antigo NÃO será apagado nem alterado.\n"
    )

    for memoria in memorias:
        texto = (
            memoria.get("texto", "")
            if isinstance(memoria, dict)
            else str(memoria)
        )

        print(f"  - {_titulo_da_frase(texto)}")

    print()

    if confirmar:
        resposta = input(
            "Digite SIM para criar essas notas agora: "
        ).strip()

        if resposta.upper() != "SIM":
            print("Cancelado — nenhuma nota foi criada.")
            return False

    notas.garantir_pastas()

    criadas = 0
    puladas = 0

    for memoria in memorias:
        if isinstance(memoria, dict):
            texto = memoria.get("texto", "")
            criada_em = memoria.get("criada_em") or notas.agora()

        else:
            texto = str(memoria)
            criada_em = notas.agora()

        texto = " ".join(str(texto).split())

        if not texto:
            continue

        titulo = _titulo_da_frase(texto)

        if notas.localizar_por_titulo(titulo, incluir_arquivo=True):
            print(f"[já existe] {titulo}")
            puladas += 1
            continue

        frontmatter = {
            "created": criada_em,
            "last_used": criada_em,
            "access_count": 0,
            "pinned": False,
        }

        caminho = (
            config.PASTA_VAULT / notas.nome_arquivo_do_titulo(titulo)
        )

        try:
            notas.escrever_nota(caminho, frontmatter, texto)
            print(f"[criada]    {titulo}")
            criadas += 1

        except (ValueError, OSError) as erro:
            print(f"[falhou]    {titulo}: {erro}")

    print(
        f"\nMigração concluída: {criadas} nota(s) criada(s), "
        f"{puladas} já existia(m)."
    )
    print(
        f"O arquivo antigo continua intacto em {ARQUIVO_ANTIGO}."
    )

    return True


if __name__ == "__main__":
    migrar(confirmar="--sem-confirmar" not in sys.argv)
