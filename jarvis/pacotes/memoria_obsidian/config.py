# Configuração da memória em vault do Obsidian. Lê o .env por conta
# própria, mesmo padrão dos outros pacotes isolados.
#
# O vault é uma pasta comum de arquivos .md — o app do Obsidian NÃO
# precisa estar instalado nem aberto. O jarvis só escreve e lê
# arquivos; se você abrir a pasta no Obsidian depois, os links
# [[assim]] já vão estar lá funcionando.
import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis.caminhos import PASTA_DADOS, garantir_pasta

load_dotenv()

# Pasta dedicada ao jarvis. Pode ser uma subpasta do vault que você já
# usa (ex: .../MeuVault/Jarvis) ou uma pasta nova. O jarvis NUNCA
# escreve fora daqui — ver notas.caminho_seguro().
_VALOR_VAULT = (os.getenv("PASTA_VAULT_JARVIS") or "").strip()

PASTA_VAULT = Path(_VALOR_VAULT).expanduser() if _VALOR_VAULT else None

# Subpasta para onde vão as notas podadas. Elas continuam existindo e
# podem voltar (ver consolidacao.reativar_nota) — arquivar nunca é
# apagar.
NOME_PASTA_ARQUIVO = "arquivo"


def pasta_arquivo():
    if PASTA_VAULT is None:
        return None

    return PASTA_VAULT / NOME_PASTA_ARQUIVO


def configurado():
    return PASTA_VAULT is not None


# --- Critérios de poda (os TRÊS precisam ser verdadeiros) ---
DIAS_SEM_USO_PARA_PODAR = int(
    os.getenv("MEMORIA_DIAS_SEM_USO", "90")
)

MAXIMO_ACESSOS_PARA_PODAR = int(
    os.getenv("MEMORIA_MAXIMO_ACESSOS", "2")
)

# --- Varredura periódica ---
INTERVALO_VARREDURA_DIAS = int(
    os.getenv("MEMORIA_INTERVALO_VARREDURA_DIAS", "7")
)

MINIMO_NOTAS_PARA_CONSOLIDAR = int(
    os.getenv("MEMORIA_MINIMO_PARA_CONSOLIDAR", "15")
)

# --- Busca ---
LIMITE_BUSCA_PADRAO = 5

# Quantas notas entram no contexto inicial da sessão. Pequeno de
# propósito: o modelo busca o resto sob demanda com
# buscar_memorias_relacionadas, em vez de carregar tudo sempre.
NOTAS_CONTEXTO_INICIAL = int(
    os.getenv("MEMORIA_NOTAS_CONTEXTO_INICIAL", "5")
)

# Corte da correspondência aproximada de título. Mesmo valor já usado
# em abrir_app_local/buscador.py e discord_jarvis/contatos.py.
CORTE_TITULO_APROXIMADO = 0.72

# Modelo usado só na consolidação (texto puro, sem voz nem UI, roda em
# background). Nada a ver com o modelo da sessão Live.
#
# Confirmado ao vivo contra a API, não escolhido de memória: o valor
# inicial deste campo era "gemini-2.5-flash", e a primeira execução
# real do teste de consolidação devolveu 404 dizendo que ele "não está
# mais disponível para novos usuários" e indicando gemini-3.6-flash no
# lugar. Nomes de modelo envelhecem — se um dia isto voltar a falhar
# com 404, liste os modelos disponíveis pela própria API em vez de
# chutar um nome novo.
#
# gemini-3.6-flash leva ~9s por resposta, contra ~1s do
# gemini-3.5-flash-lite, e isso é indiferente aqui: a consolidação roda
# numa thread de fundo, sem ninguém esperando. A qualidade do resumo
# importa mais, porque depois dele os originais são descartados.
MODELO_CONSOLIDACAO = os.getenv(
    "MEMORIA_MODELO_CONSOLIDACAO",
    "gemini-3.6-flash",
)

TIMEOUT_CONSOLIDACAO_SEGUNDOS = 120

# Retentativas da chamada de resumo. Erros temporarios (503 de
# modelo sobrecarregado, 429 de limite) apareceram no primeiro teste
# real; sem retentativa, um pico de demanda pulava a consolidacao da
# semana inteira. A espera cresce a cada tentativa.
TENTATIVAS_CONSOLIDACAO = 3
ESPERA_ENTRE_TENTATIVAS_SEGUNDOS = 8

# Arquivo de controle da última varredura. Fica em dados/, não no
# vault: é estado técnico do app, não uma memória do usuário — e o
# vault deve conter só notas.
ARQUIVO_CONTROLE = (
    garantir_pasta(PASTA_DADOS) / "memoria_obsidian_controle.json"
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações. Ver docs/INTEGRATION.md, seção "Tela de
# configurações".
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
