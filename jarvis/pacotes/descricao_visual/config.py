# Carrega as variáveis de ambiente do arquivo .env — desacoplado de
# jarvis/nucleo/config.py de propósito, mesmo padrão dos demais
# pacotes isolados.
from dotenv import dotenv_values, load_dotenv

import os

from jarvis.caminhos import CAMINHO_ENV

load_dotenv()

# ============================================================
# QUAL PROVEDOR DE VISÃO DESCREVE A TELA / A CÂMERA
# ============================================================
# Dois provedores possíveis: "gemini" (padrão) e "mistral". Resolvido
# a cada chamada em provedor_visao() logo abaixo:
#
#   1. DESCRICAO_VISUAL_PROVEDOR no .env, se estiver definida com um
#      valor válido, MANDA — é a porta manual do usuário.
#   2. Sem ela, o padrão é FIXO em "gemini".
#
# POR QUE O PADRÃO É O GEMINI: medido ao vivo enquanto este pacote era
# escrito, a chave da Mistral deste projeto responde 429 com
# "x-ratelimit-limit-req-minute: 0" — o limite é ZERO, a cota do tier
# gratuito acabou; não é espera passageira. O Gemini descreveu um
# print real de 467 KB em 5,7s na mesma hora, com a chave que o
# projeto já exige para funcionar. Reaproveitar a Mistral (que
# identificacao_visual já usa) seria mais elegante, e continua sendo
# uma variável de distância — mas entregar como padrão uma chave sem
# cota seria entregar uma ferramenta que não funciona.
#
# POR QUE ESTE PACOTE **NÃO** SEGUE A REGRA AUTOMÁTICA DE
# jarvis/pacotes/identificacao_visual/ (lá o padrão é sempre o oposto
# do cérebro de voz ativo, para a segunda opinião não virar o mesmo
# modelo confirmando a si mesmo): descrever_tela/descrever_camera não
# prometem independência nenhuma. Não são uma segunda opinião — são a
# visão PRIMÁRIA do modo de voz local, o porte dos antigos
# analisar_tela/analisar_camera. Não existe fonte anterior de quem
# elas precisem discordar, então amarrá-las ao cérebro ativo só
# mandaria a descrição para uma chave sem cota no modo Gemini,
# quebrando a ferramenta sem ganho nenhum.
#
# A ASSIMETRIA É DELIBERADA E É SÓ DO PADRÃO AUTOMÁTICO: a variável
# manual continua sendo UMA só para os dois pacotes, então uma escolha
# explícita do usuário nunca separa as duas ferramentas de visão em
# provedores diferentes — só a política automática separa, e por um
# motivo documentado.
PROVEDORES_VISAO = ("gemini", "mistral")


# Lê a escolha MANUAL do usuário, ou None quando ela não existe ou não
# vale. Lê o arquivo .env do disco a cada chamada (e não só o
# os.environ) pelo mesmo motivo de provedor_ativo() em
# jarvis/nucleo/config.py: a tela de configurações salva com set_key(),
# que escreve no arquivo e nunca atualiza o os.environ do processo já
# em execução.
#
# Cópia local do mesmo helper de jarvis/pacotes/identificacao_visual/
# config.py, seguindo a convenção de duplicação por pacote deste
# projeto — os dois pacotes são isolados e cada um lê o próprio .env.
def provedor_forcado():
    valores = dotenv_values(CAMINHO_ENV) if CAMINHO_ENV.exists() else {}

    bruto = valores.get("DESCRICAO_VISUAL_PROVEDOR")

    if bruto is None:
        bruto = os.getenv("DESCRICAO_VISUAL_PROVEDOR")

    valor = (bruto or "").strip().lower()

    if valor in PROVEDORES_VISAO:
        return valor

    return None


# O provedor efetivo DESTA chamada. Valor inválido no .env cai no
# padrão, nunca deixa o provedor indefinido — mesma regra de segurança
# de PROVEDOR_IA: um erro de digitação não troca de provedor sozinho.
def provedor_visao():
    return provedor_forcado() or "gemini"


# Chave do Gemini — a MESMA que jarvis/nucleo/config.py já lê. Não é
# uma credencial nova.
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

# Modelo de visão do Gemini. O flash-lite foi escolhido por ser o mais
# rápido e barato da família com visão, e confirmado ao vivo neste
# projeto (5,7s para um print de 467 KB) — os modelos maiores estavam
# devolvendo 503 por alta demanda no mesmo momento.
MODELO_GEMINI = os.getenv(
    "DESCRICAO_VISUAL_MODELO_GEMINI",
    "gemini-3.5-flash-lite",
)

# Reaproveita a MESMA MISTRAL_API_KEY que jarvis/pacotes/
# identificacao_visual/ já usa — nunca cria uma segunda chave para a
# mesma credencial.
MISTRAL_API_KEY = os.getenv(
    "MISTRAL_API_KEY"
)

# Modelo separado do de identificacao_visual de propósito: as duas
# tarefas são diferentes (descrever uma cena inteira vs. identificar
# um objeto), e poder trocar uma sem mexer na outra é o ponto.
MODELO_MISTRAL = os.getenv(
    "DESCRICAO_VISUAL_MODELO_MISTRAL",
    "mistral-medium-latest",
)

# Tempo limite da chamada de visão, valendo para os DOIS provedores
# (na Mistral é o timeout do requests; no Gemini vira o timeout do
# HttpOptions do SDK, que por padrão não tem nenhum). Maior que os 20s de
# identificacao_visual porque um print de tela cheia costuma ser bem
# mais pesado que um frame de webcam, e descrever uma tela com muito
# texto rende uma resposta mais longa.
TIMEOUT_SEGUNDOS = int(
    os.getenv(
        "DESCRICAO_VISUAL_TIMEOUT_SEGUNDOS",
        "30",
    )
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações — ver docs/INTEGRATION.md, seção "Tela de
# configurações". GEMINI_API_KEY e MISTRAL_API_KEY não aparecem aqui:
# já são exibidas nas seções "Gemini / Núcleo do ALFRED" e "Segunda
# Opinião Visual (Mistral)", e dois campos sensíveis para a mesma
# credencial só confundiria.
def config_schema():
    return [
        {
            "nome": "DESCRICAO_VISUAL_PROVEDOR",
            "rotulo": (
                "Provedor de visão (vale para descrever tela/câmera e "
                "para a segunda opinião visual). Em branco: descrever "
                "usa o Gemini, e a segunda opinião usa automaticamente "
                "o provedor oposto ao cérebro de voz ativo"
            ),
            "sensivel": False,
            "obrigatoria": False,
            "opcoes": [
                ("", "Automático (recomendado)"),
                ("gemini", "Forçar Gemini"),
                ("mistral", "Forçar Mistral"),
            ],
        },
        {
            "nome": "DESCRICAO_VISUAL_MODELO_GEMINI",
            "rotulo": (
                "Modelo de visão do Gemini "
                "(padrão: gemini-3.5-flash-lite)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DESCRICAO_VISUAL_MODELO_MISTRAL",
            "rotulo": (
                "Modelo de visão da Mistral "
                "(padrão: mistral-medium-latest)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "DESCRICAO_VISUAL_TIMEOUT_SEGUNDOS",
            "rotulo": (
                "Tempo limite da chamada de visão, em segundos "
                "(padrão: 30 — vale para os dois provedores)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
