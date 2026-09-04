# Único lugar do projeto que sabe onde ficam a raiz e a pasta de
# dados. Todo módulo que precisa de um arquivo fora do próprio código
# (memória, cache, log, fila) importa daqui em vez de contar quantos
# ".parent" faltam até a raiz — assim, mover uma pasta de lugar não
# quebra mais nenhum caminho.
from pathlib import Path

# jarvis/caminhos.py -> jarvis/ -> raiz do projeto.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent

# Arquivo de credenciais, lido pelos config.py de cada pacote.
CAMINHO_ENV = RAIZ_PROJETO / ".env"

# Preferências locais da máquina (hoje só "interrupcao") — ver
# jarvis/nucleo/preferencias.py.
CAMINHO_CONFIG_JSON = RAIZ_PROJETO / "config.json"

# Pasta de código do projeto (jarvis/). Este arquivo mora dentro
# dela, então é o próprio pai — nunca recalculado a partir da raiz.
PASTA_JARVIS = Path(__file__).resolve().parent

# Tudo que o app gera enquanto roda. Separado do código de propósito:
# o que está em jarvis/ é fonte, o que está aqui é estado desta
# máquina.
PASTA_DADOS = RAIZ_PROJETO / "dados"
PASTA_LOGS = PASTA_DADOS / "logs"

# Perfis do jarvis: uma pasta autocontida por perfil
# (dados/perfis/<slug>/), mais o índice leve dados/perfis/indice.json
# que só existe pra popular o select da interface rapidamente. A pasta
# de cada perfil é a fonte da verdade; o índice é derivado dela e
# regravado a cada criação/edição/exclusão — ver jarvis/nucleo/perfis/.
#
# Fica em dados/, e não em jarvis/, porque um perfil criado pelo
# usuário é estado gerado por esta máquina, não fonte do projeto — a
# mesma regra que já vale para dados/memoria.json e dados/agenda.json,
# que também são versionados apesar de morarem aqui.
PASTA_PERFIS = PASTA_DADOS / "perfis"


def garantir_pasta(caminho):
    """
    Cria a pasta (e as pastas acima dela) se ainda não existir, e
    devolve o mesmo caminho — para ser usado direto na definição de
    uma constante de arquivo.
    """
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho
