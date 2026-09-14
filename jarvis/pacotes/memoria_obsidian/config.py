import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis.caminhos import PASTA_DADOS, garantir_pasta
from jarvis.nucleo import modelos

load_dotenv()

_VALOR_VAULT = (os.getenv("PASTA_VAULT_JARVIS") or "").strip()

PASTA_VAULT = Path(_VALOR_VAULT).expanduser() if _VALOR_VAULT else None

NOME_PASTA_ARQUIVO = "arquivo"


def pasta_arquivo():
    if PASTA_VAULT is None:
        return None

    return PASTA_VAULT / NOME_PASTA_ARQUIVO


def configurado():
    return PASTA_VAULT is not None


DIAS_SEM_USO_PARA_PODAR = int(
    os.getenv("MEMORIA_DIAS_SEM_USO", "90")
)

MAXIMO_ACESSOS_PARA_PODAR = int(
    os.getenv("MEMORIA_MAXIMO_ACESSOS", "2")
)

INTERVALO_VARREDURA_DIAS = int(
    os.getenv("MEMORIA_INTERVALO_VARREDURA_DIAS", "7")
)

MINIMO_NOTAS_PARA_CONSOLIDAR = int(
    os.getenv("MEMORIA_MINIMO_PARA_CONSOLIDAR", "15")
)

LIMITE_BUSCA_PADRAO = 5

NOTAS_CONTEXTO_INICIAL = int(
    os.getenv("MEMORIA_NOTAS_CONTEXTO_INICIAL", "5")
)

CORTE_TITULO_APROXIMADO = 0.72

MODELO_CONSOLIDACAO = modelos.modelo("subagentes.consolidacao_memoria")

TIMEOUT_CONSOLIDACAO_SEGUNDOS = 120

TENTATIVAS_CONSOLIDACAO = 3
ESPERA_ENTRE_TENTATIVAS_SEGUNDOS = 8

ARQUIVO_CONTROLE = (
    garantir_pasta(PASTA_DADOS) / "memoria_obsidian_controle.json"
)


def config_schema():
    return [
        {
            "nome": "PASTA_VAULT_JARVIS",
            "rotulo": "Pasta do vault (uma pasta dedicada ao jarvis)",
            "sensivel": False,
            "obrigatoria": True,
        },
        {
            "nome": "MEMORIA_DIAS_SEM_USO",
            "rotulo": "Dias sem uso para arquivar uma nota (padrão: 90)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MEMORIA_MAXIMO_ACESSOS",
            "rotulo": "Arquivar só notas com menos acessos que este número (padrão: 2)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MEMORIA_INTERVALO_VARREDURA_DIAS",
            "rotulo": "De quantos em quantos dias varrer (padrão: 7)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MEMORIA_MINIMO_PARA_CONSOLIDAR",
            "rotulo": "Notas arquivadas necessárias para consolidar (padrão: 15)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "MEMORIA_NOTAS_CONTEXTO_INICIAL",
            "rotulo": "Notas carregadas no início da sessão (padrão: 5)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
