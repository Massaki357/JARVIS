# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão dos demais pacotes
# isolados.
from dotenv import dotenv_values, load_dotenv

import os

from jarvis.caminhos import CAMINHO_ENV

load_dotenv()

# ============================================================
# QUAL PROVEDOR RESPONDE A SEGUNDA OPINIÃO VISUAL
# ============================================================
# Dois provedores possíveis: "gemini" e "mistral". A escolha NÃO é um
# valor fixo, e sim uma POLÍTICA, resolvida a cada chamada em
# provedor_visao() logo abaixo:
#
#   1. Se DESCRICAO_VISUAL_PROVEDOR estiver definida no .env com um
#      valor válido, ela MANDA. É a porta manual do usuário para
#      forçar um provedor específico, e sobrepõe a regra automática.
#   2. Sem essa variável (o caso normal), vale a REGRA AUTOMÁTICA: o
#      provedor de visão é sempre o OPOSTO do cérebro de voz ativo —
#      Mistral quando PROVEDOR_IA=gemini, Gemini nos demais casos
#      (openai e local).
#
# POR QUE A REGRA AUTOMÁTICA EXISTE: esta ferramenta tem um propósito
# só, ser uma fonte INDEPENDENTE de quem já respondeu. Com um padrão
# fixo em Gemini, no modo de voz Gemini a "segunda opinião" vira o
# Gemini confirmando a si mesmo, e a ferramenta deixa de cumprir a
# própria promessa EM SILÊNCIO: ela responde normalmente, nada falha,
# e o problema só aparece se alguém estiver prestando atenção. Amarrar
# o padrão ao cérebro ativo é o que fecha esse furo silencioso. Não é
# mágica implícita: é esta política, escrita aqui e documentada em
# CLAUDE.md e em docs/INTEGRATION.md.
#
# CUIDADO COM A CHAVE DA MISTRAL: medido ao vivo, a MISTRAL_API_KEY
# deste projeto responde 429 com "x-ratelimit-limit-req-minute: 0" —
# a cota do tier gratuito acabou, não é throttle passageiro. Enquanto
# ela não voltar, no modo de voz Gemini esta ferramenta vai FALHAR em
# vez de responder. Falhar aqui é barulhento e honesto (o cliente
# devolve prompts.VISAO_INDISPONIVEL, que manda o cérebro avisar o
# usuário que não confirmou com uma segunda fonte), enquanto o padrão
# fixo em Gemini era silencioso e enganoso — foi exatamente por isso
# que a regra mudou. Quem preferir a resposta menos independente à
# falha põe DESCRICAO_VISUAL_PROVEDOR=gemini no .env, que existe para
# isso.
#
# ASSIMETRIA PROPOSITAL com jarvis/pacotes/descricao_visual/: aquele
# pacote continua com padrão FIXO em "gemini", porque descrever_tela/
# descrever_camera não prometem independência nenhuma — são a visão
# primária do modo local, e mandá-las para uma chave sem cota só
# quebraria a ferramenta sem ganho nenhum. A variável manual continua
# sendo UMA só (DESCRICAO_VISUAL_PROVEDOR) para os dois pacotes: uma
# escolha manual do usuário nunca separa os dois; só a política
# automática separa, e de propósito.
PROVEDORES_VISAO = ("gemini", "mistral")


# Lê a escolha MANUAL do usuário, ou None quando ela não existe ou não
# vale. Lê o arquivo .env do disco a cada chamada (e não só o
# os.environ) pelo mesmo motivo de provedor_ativo() em
# jarvis/nucleo/config.py: a tela de configurações salva com set_key(),
# que escreve no arquivo e nunca atualiza o os.environ do processo já
# em execução — sem ler o disco, trocar o provedor na tela só valeria
# depois de reiniciar o app.
#
# Valor inválido (erro de digitação) é tratado como ausência: cai na
# regra automática, nunca num provedor sorteado. Mesma disciplina de
# PROVEDOR_IA — um .env torto não troca de provedor sozinho.
def provedor_forcado():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    bruto = valores.get("DESCRICAO_VISUAL_PROVEDOR")

    if bruto is None:
        bruto = os.getenv("DESCRICAO_VISUAL_PROVEDOR")

    valor = (bruto or "").strip().lower()

    if valor in PROVEDORES_VISAO:
        return valor

    return None


# O provedor efetivo DESTA chamada. Resolvido a cada chamada e nunca
# fixado na importação: assim tanto trocar o cérebro de voz quanto
# definir a variável manual valem já na próxima chamada, sem reiniciar
# o app.
def provedor_visao():
    forcado = provedor_forcado()

    if forcado:
        return forcado

    # Import adiado de propósito: mantém este pacote sem depender de
    # jarvis/nucleo/config.py no topo do arquivo (convenção de pacote
    # isolado) e afasta qualquer risco de ciclo de importação.
    from jarvis.nucleo import config as config_nucleo

    # A regra em uma linha: o provedor de visão nunca é o mesmo
    # cérebro que está raciocinando.
    if config_nucleo.provedor_ativo() == "gemini":
        return "mistral"

    return "gemini"


# Chave do Gemini — a MESMA que jarvis/nucleo/config.py já lê. Não é
# uma credencial nova.
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

# Modelo de visão do Gemini. Variável própria (e não a do
# descricao_visual) porque as duas tarefas são diferentes: descrever
# uma cena inteira vs. identificar um objeto específico. Poder ajustar
# uma sem mexer na outra é o ponto — o mesmo motivo pelo qual o modelo
# da Mistral já era separado.
MODELO_GEMINI = os.getenv(
    "IDENTIFICACAO_VISUAL_MODELO_GEMINI",
    "gemini-3.5-flash-lite",
)

# Reaproveita a MESMA variável MISTRAL_API_KEY que já existia no
# .env do projeto (de uma tarefa anterior) — nunca cria uma segunda
# chave/nome pra mesma credencial.
MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY"
)

# Modelo de visão da Mistral usado como segunda opinião independente
# do Gemini para identificação de objeto genérico.
#
# O Pixtral (o antigo modelo de visão dedicado da Mistral, que era o
# pedido original aqui) está DESCONTINUADO — confirmado na
# documentação oficial de depreciação da Mistral:
# pixtral-12b-2409 foi retirado em 31/12/2025, pixtral-large-2411 em
# 31/05/2026. A capacidade de visão passou a fazer parte dos modelos
# generalistas atuais (Mistral Large/Medium/Small), não existe mais
# um modelo de visão dedicado separado no catálogo da Mistral.
# mistral-medium-latest foi uma escolha CONSCIENTE do usuário diante
# disso (substituto direto do antigo Pixtral Large segundo a própria
# doc de depreciação da Mistral) — não um default assumido sem
# checar. Ver CLAUDE.md para o histórico completo dessa decisão.
MODELO_MISTRAL_VISION = os.getenv(
    "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
    "mistral-medium-latest",
)

# Tempo limite, em segundos, para a chamada HTTP à Mistral.
TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
        "20",
    )
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — não é usado por mais nada além disso. Ver
# docs/INTEGRATION.md, seção "Tela de configurações".
def config_schema():
    return [
        {
            "nome": "MISTRAL_API_KEY",
            "rotulo": (
                "Chave de API da Mistral — usada pela segunda opinião "
                "visual sempre que o cérebro de voz ativo for o Gemini "
                "(regra automática: a segunda opinião nunca é o mesmo "
                "cérebro que respondeu), ou quando "
                "DESCRICAO_VISUAL_PROVEDOR=mistral"
            ),
            "sensivel": True,
            # Não é marcada como obrigatória porque nos modos de voz
            # openai e local a regra automática manda a segunda
            # opinião para o Gemini, e o pacote funciona sem nenhuma
            # chave da Mistral. Cobrá-la sempre faria a tela exigir
            # uma credencial que naquele modo não é usada.
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_MODELO_GEMINI",
            "rotulo": (
                "Modelo de visão do Gemini para a segunda opinião "
                "(padrão: gemini-3.5-flash-lite)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_MODELO_MISTRAL",
            "rotulo": "Modelo de visão da Mistral (padrão: mistral-medium-latest)",
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "IDENTIFICACAO_VISUAL_TIMEOUT_SEGUNDOS",
            "rotulo": "Tempo limite da chamada, em segundos (padrão: 20)",
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
