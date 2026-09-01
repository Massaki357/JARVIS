# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão de jarvis/pacotes/rede_jarvis/config.py e
# jarvis/pacotes/casa_inteligente/config.py (cada pacote isolado lê o .env sozinho).
from dotenv import load_dotenv

import os

load_dotenv()

# Tempo limite, em segundos, pra abrir o navegador (Playwright +
# Chromium) na primeira vez que uma ação de navegador é pedida — só é
# relevante nessa primeira chamada, já que a sessão fica de pé e é
# reaproveitada depois (ver jarvis/pacotes/navegador_jarvis/sessao.py).
TIMEOUT_INICIO_SEGUNDOS = int(
    os.getenv(
        "NAVEGADOR_TIMEOUT_INICIO",
        "30",
    )
)

# Tempo limite, em segundos, pra uma única ação (abrir site, buscar e
# tocar música, pausar, retomar) terminar.
TIMEOUT_ACAO_SEGUNDOS = int(
    os.getenv(
        "NAVEGADOR_TIMEOUT_ACAO",
        "30",
    )
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — ver docs/INTEGRATION.md, seção "Tela de
# configurações". Nenhuma variável deste pacote é sensível ou
# obrigatória — ambas têm um valor padrão funcional.
def config_schema():
    return [
        {
            "nome": "NAVEGADOR_TIMEOUT_INICIO",
            "rotulo": (
                "Tempo limite para abrir o navegador na primeira "
                "vez, em segundos (padrão: 30)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "NAVEGADOR_TIMEOUT_ACAO",
            "rotulo": (
                "Tempo limite por ação de navegador, em segundos "
                "(padrão: 30)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
