import os
from dotenv import dotenv_values, load_dotenv

from jarvis.caminhos import CAMINHO_ENV

load_dotenv()

# ============================================================
# PROVEDOR DE IA ATIVO
# ============================================================
# Qual cérebro de voz o ALFRED usa: "gemini"
# (jarvis/cerebro/gemini/cliente_live.py), "openai"
# (jarvis/cerebro/openai_realtime/cliente_realtime.py) ou "local"
# (jarvis/cerebro/voz_local/cliente_local.py, o alfred-server rodando em
# Docker nesta máquina). A troca é só esta variável no .env — nenhum
# outro arquivo muda, porque os três workers expõem a mesma API
# pública.
#
# ATENÇÃO ao modo "local": o protocolo do alfred-server troca ARQUIVOS
# DE ÁUDIO e nada mais, então nele não existem ferramentas, perfis,
# prompt de sistema nem o gate da palavra-chave de autenticação. Não é
# uma pendência a implementar depois — não há canal para isso. Ver o
# cabeçalho de jarvis/cerebro/voz_local/cliente_local.py.
#
# Qualquer valor fora de PROVEDORES_VALIDOS cai no Gemini, de
# propósito: um .env com erro de digitação não deve trocar de provedor
# sozinho.
#
# Este valor é o lido na IMPORTAÇÃO do módulo (início do app) — mantido
# só como referência/compatibilidade. A decisão de verdade sobre qual
# worker usar é sempre feita por usar_provedor_openai() logo abaixo,
# que relê o .env do disco a cada chamada, não este valor cacheado.
PROVEDOR_IA = os.getenv("PROVEDOR_IA", "gemini").strip().lower()


# Relê PROVEDOR_IA direto do arquivo .env EM DISCO a cada chamada, em
# vez de usar o valor cacheado acima (fixado na importação do módulo,
# ou seja, na abertura do app). Isso é o que permite trocar o cérebro
# de voz na tela de configurações (jarvis/pacotes/configuracoes/) e a
# PRÓXIMA chamada iniciada (jarvis/ui/janela_principal.py::
# _classe_do_worker, chamado só no início de cada chamada) já usar o
# provedor novo, sem precisar fechar e reabrir o app inteiro.
#
# set_key() (usado por jarvis/pacotes/configuracoes/env_io.py pra
# salvar) só escreve no arquivo .env — nunca atualiza os.environ do
# processo já em execução — então ler de os.getenv aqui devolveria
# sempre o valor antigo. dotenv_values(CAMINHO_ENV) lê o arquivo do
# zero toda vez, contornando esse cache (mesma função que
# env_io.ler_valores() já usa pra popular a própria tela).
#
# Isto é seguro só porque a leitura acontece sempre ENTRE chamadas —
# nenhuma sessão de voz já em andamento troca de provedor sozinha no
# meio (o worker inteiro é recriado do zero a cada chamada). Não é uma
# terceira porta de entrada pra OpenAI: continua sendo só esta mesma
# variável de .env que já decidia isso, agora só lida num momento
# diferente.
# Cérebros de voz reconhecidos, como (valor no .env, rótulo na tela).
# FONTE ÚNICA: quem mostra um select de cérebro lê daqui — a tela de
# configurações (via config_schema() logo abaixo) e o select da tela
# principal (jarvis/ui/painel_provedor.py).
#
# Isto virou uma lista só depois de um bug real: o painel da tela
# principal mantinha a própria cópia com dois itens, e quando o
# terceiro cérebro entrou ele continuou oferecendo apenas dois — o
# usuário foi selecionar o servidor local e a opção não existia lá.
# O comentário daquele arquivo até dizia que a cópia existia "pra não
# virar uma segunda fonte de verdade divergente", que é exatamente no
# que ela deu. Nunca duplique esta lista: importe-a.
OPCOES_PROVEDOR = (
    ("gemini", "Gemini"),
    ("openai", "OpenAI"),
    ("local", "Servidor local (alfred-server)"),
)

# Derivado da lista acima, nunca escrito à mão em paralelo. Qualquer
# valor fora daqui cai em "gemini" (ver provedor_ativo), de propósito:
# um .env com erro de digitação nunca deve trocar de provedor sozinho.
PROVEDORES_VALIDOS = tuple(valor for valor, _ in OPCOES_PROVEDOR)


# Relê PROVEDOR_IA direto do arquivo .env EM DISCO a cada chamada, em
# vez de usar o valor cacheado na importação do módulo (ver o
# comentário longo acima). Devolve sempre um dos PROVEDORES_VALIDOS.
def provedor_ativo():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    valor = (valores.get("PROVEDOR_IA") or "gemini").strip().lower()

    if valor in PROVEDORES_VALIDOS:
        return valor

    return "gemini"


# Mantida como estava para não mexer em quem já a chama (hoje
# _classe_do_worker, em jarvis/ui/janela_principal.py). Continua
# significando exatamente a mesma coisa: só "openai" é openai.
def usar_provedor_openai():
    return provedor_ativo() == "openai"


# Terceiro cérebro: o servidor local (alfred-server), ver
# jarvis/cerebro/voz_local/. Mesmíssima porta de entrada dos outros dois — só
# esta variável de .env decide, nada mais no projeto o alcança.
def usar_provedor_local():
    return provedor_ativo() == "local"


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ============================================================
# NOME DO JARVIS
# ============================================================
# Nome de identidade falado/exibido pelo assistente — cada usuário
# pode trocar (tela principal, jarvis/ui/painel_nome.py, ou a tela de
# configurações). Padrão "ALFRED", igual sempre foi.
#
# Mesmo valor cacheado na importação (compatibilidade/referência) que
# PROVEDOR_IA logo acima — a decisão de verdade é sempre
# obter_nome_jarvis(), que relê o .env do disco.
NOME_JARVIS = (os.getenv("NOME_JARVIS", "ALFRED").strip() or "ALFRED")


# Relê NOME_JARVIS direto do .env EM DISCO a cada chamada — mesmo
# motivo e mesma técnica de usar_provedor_openai() logo acima: permite
# trocar o nome (tela principal ou configurações) e a instrução de
# sistema da PRÓXIMA chamada (jarvis/nucleo/prompts/_carregar) já usar
# o nome novo, sem reiniciar o app. Nunca devolve vazio — um .env com
# a variável ausente ou em branco cai no nome padrão "ALFRED".
def obter_nome_jarvis():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    return (valores.get("NOME_JARVIS") or "ALFRED").strip() or "ALFRED"

# Controla se o gate de autenticação por palavra-chave (ver a seção
# "AUTENTICAÇÃO" de instrucao_sistema, em jarvis/cerebro/gemini/cliente_live.py)
# é exigido dentro de uma chamada. Padrão True — o comportamento de
# segurança já existente nunca muda sozinho; só fica desativado se o
# usuário explicitamente colocar EXIGIR_AUTENTICACAO=false no .env.
EXIGIR_AUTENTICACAO = os.getenv(
    "EXIGIR_AUTENTICACAO",
    "true",
).strip().lower() not in ("false", "0", "nao", "não")

# Tempo, em segundos, sem atividade REAL (fala do ALFRED ou execução
# de uma função — nunca só ruído captado pelo microfone) durante uma
# chamada ativa antes de encerrá-la automaticamente. Ver
# GeminiLiveWorker.executar/timestamp_ultima_atividade em
# jarvis/cerebro/gemini/cliente_live.py.
TIMEOUT_INATIVIDADE_SEGUNDOS = int(
    os.getenv(
        "TIMEOUT_INATIVIDADE_SEGUNDOS",
        "300",
    )
)


# Descreve as variáveis de .env deste módulo pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os
# campos automaticamente — mesmo contrato dos demais pacotes (ver
# docs/INTEGRATION.md, seção "Tela de configurações"), só que aqui em
# jarvis/nucleo/config.py em vez de jarvis/pacotes/<pacote>/config.py,
# já que este módulo não é um pacote de tools. Lacuna fechada: era
# anotado como "próximo passo natural, não esquecimento" — cobria só
# rede_jarvis/casa_inteligente/delegacao_ia/admin_terminal/etc, nunca
# a própria chave do Gemini. GEMINI_LIVE_MODEL/GEMINI_VOICE ficam de
# fora de propósito — são constantes Python fixas, não lidas de
# variável de ambiente nenhuma (ver o comentário logo abaixo delas:
# "swap the active value" em vez de virar uma variável de .env).
def config_schema():
    return [
        {
            "nome": "GEMINI_API_KEY",
            "rotulo": "Chave da API do Gemini (obrigatória para o app funcionar)",
            "sensivel": True,
            "obrigatoria": True,
        },
        {
            "nome": "NOME_JARVIS",
            "rotulo": (
                "Nome de identidade do assistente (padrão: ALFRED — "
                "vale já na próxima chamada; também editável direto "
                "na tela principal)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "EXIGIR_AUTENTICACAO",
            "rotulo": (
                "Exigir a palavra-chave de autenticação por voz "
                "(padrão: true — nunca desative sem entender o risco)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "PROVEDOR_IA",
            "rotulo": (
                "Cérebro de voz ativo (vale já na próxima chamada, "
                "sem precisar reiniciar o app)"
            ),
            "sensivel": False,
            "obrigatoria": False,
            # "opcoes": campo de seleção em vez de texto livre — só
            # os dois valores que usar_provedor_openai() realmente
            # reconhece. A primeira opção ("gemini") é também o
            # fallback real do os.getenv(..., "gemini") logo acima:
            # se o valor salvo no .env não bater com nenhuma opção
            # (variável ausente, ou digitada errado antes desta tela
            # existir), a tela seleciona esta primeira opção — o
            # mesmo comportamento que o app já teria em runtime.
            "opcoes": list(OPCOES_PROVEDOR),
        },
        {
            "nome": "TIMEOUT_INATIVIDADE_SEGUNDOS",
            "rotulo": (
                "Tempo sem atividade real antes de encerrar a "
                "chamada sozinho, em segundos (padrão: 300)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]

# Modelo usado pelo ALFRED
GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"

# Modelo alternativo: só é tentado quando GEMINI_LIVE_MODEL falha ao
# CONECTAR (não numa falha no meio de uma chamada já conectada — ver
# GeminiLiveWorker._conectar_sessao_gemini em jarvis/cerebro/gemini/cliente_live.py).
# Só se este também falhar é que o cérebro reserva assume a chamada
# inteira — pedido explícito do usuário. Nome confirmado ao vivo contra
# client.models.list() antes de usar (não adivinhado), junto com as
# outras opções comentadas abaixo.
GEMINI_LIVE_MODEL_FALLBACK = "gemini-2.5-flash-native-audio-preview-12-2025"

# ============================================================
# MODELOS DISPONÍVEIS PARA TESTE
# ============================================================
#MODELO = "gemini-2.5-flash-native-audio-preview-12-2025"
#MODELO = “gemini-2.5-flash-native-audio-preview-09-2025”
#MODELO = "gemini-3.1-flash-live-preview"


# Voz usada pelo ALFRED
GEMINI_VOICE = "Charon"

# ============================================================
# VOZES DISPONÍVEIS PARA TESTE
# ============================================================
#
# Zephyr   - brilhante
# Puck     - animada
# Charon   - informativa
# Kore     - feminia e firme
# Fenrir   - empolgada
# Leda     - jovem
# Orus     - firme
# Aoede    - leve
# Callirrhoe - descontraída
# Autonoe  - brilhante
# Enceladus - suave/sussurrante
# Iapetus  - clara
# Umbriel  - descontraída
# Algieba  - suave
# Despina  - suave
# Erinome  - clara
# Algenib  - rouca
# Rasalgethi - informativa
# Laomedeia - animada
# Achernar - suave
# Alnilam  - firme
# Schedar  - equilibrada
# Gacrux   - madura
# Pulcherrima - direta
# Achird   - amigável
# Zubenelgenubi - casual
# Vindemiatrix - feminina gentil
# Sadachbia - animada
# Sadaltager - experiente
# Sulafat  - calorosa


# ============================================================
# CONFIGURAÇÃO DA OPENAI (Realtime API)
# ============================================================
# Usadas só quando PROVEDOR_IA = "openai". A chave é a MESMA
# OPENAI_API_KEY que jarvis/pacotes/delegacao_ia/ já usa para a
# segunda opinião — não existe uma segunda chave.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Modelo Realtime usado pelo ALFRED quando PROVEDOR_IA = "openai".
OPENAI_REALTIME_MODEL = "gpt-realtime"

# ============================================================
# MODELOS REALTIME DISPONÍVEIS PARA TESTE
# ============================================================
#OPENAI_REALTIME_MODEL = "gpt-realtime"
#OPENAI_REALTIME_MODEL = "gpt-4o-realtime-preview"
#OPENAI_REALTIME_MODEL = "gpt-4o-mini-realtime-preview"

# Voz usada pelo ALFRED quando PROVEDOR_IA = "openai".
OPENAI_VOICE = "marin"

# ============================================================
# VOZES DISPONÍVEIS PARA TESTE (Realtime API)
# ============================================================
# alloy    - neutra
# ash      - grave
# ballad   - suave
# coral    - calorosa
# echo     - firme
# sage     - equilibrada
# shimmer  - brilhante
# verse    - versátil
# marin    - natural
# cedar    - natural/grave
