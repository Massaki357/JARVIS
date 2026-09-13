# Carrega as variáveis de ambiente do arquivo .env. Módulo próprio,
# com seu próprio load_dotenv() — mesma convenção de todo pacote
# isolado deste projeto.
from dotenv import load_dotenv

import os

load_dotenv()

# GROQ_API_KEY já existe no .env deste projeto (delegacao_ia e o
# roteamento hierárquico já a leem) — aqui é só reaproveitada pela
# mesma variável, nunca duplicada com um nome diferente. Por isso ela
# NÃO aparece em config_schema(): já é exibida na seção "Delegação de
# IA" da tela de configurações, e dois campos sensíveis mostrando a
# mesma chave seria confuso sem necessidade.
GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

# Modelo do sub-agente. O mesmo já usado e confirmado funcionando nos
# outros dois caminhos de Groq deste projeto — e, especificamente
# para este pacote, confirmado ao vivo suportando response_format
# (modo JSON), que é como a resposta dele é lida.
MODELO = os.getenv(
    "AGENTE_FERRAMENTAS_MODELO",
    "openai/gpt-oss-20b",
)

# Timeout da consulta ao sub-agente, em segundos.
#
# Mais folgado que os 8s de delegacao_ia de propósito: esta chamada
# acontece no MEIO de um turno de voz, com o usuário esperando, mas o
# custo de desistir cedo demais é alto — o cérebro fica sem saber qual
# ferramenta usar e tem que se virar sem ela. Ainda é curto o
# bastante para não deixar a conversa parada.
TIMEOUT_SEGUNDOS = 12

# Quantas ferramentas o sub-agente pode apontar de uma vez. A
# primeira é a recomendada (volta com as instruções completas de
# execução); as outras voltam como alternativas de uma linha, para o
# cérebro decidir se alguma serve melhor.
#
# 3 e não mais: uma lista maior deixa de ser uma recomendação e vira
# um segundo catálogo dentro da resposta, que é justamente o que este
# sub-agente existe para evitar.
LIMITE_CANDIDATOS = 3

# Tentativas quando a Groq responde 429 (limite de uso). Mesmo motivo
# do roteamento hierárquico: a janela reabre em ~1s e o corpo do erro
# diz isso, então repetir resolve — esperar o usuário repetir a frase
# não. Ver jarvis/servicos/agentes/erros.py.
TENTATIVAS_LIMITE = 3

ESPERA_BASE_SEGUNDOS = 1.0
ESPERA_MAXIMA_SEGUNDOS = 4.0


def _ler_bool(nome, padrao=False):
    bruto = (os.getenv(nome) or "").strip().lower()

    if not bruto:
        return padrao

    return bruto in ("1", "true", "sim", "yes", "on")


# Qual descrição de cada ferramenta vai no catálogo que o sub-agente
# lê. As duas opções são descrições reais da mesma ferramenta, em
# profundidades diferentes:
#
#   False (padrão) — o resumo de uma linha, a mesma fonte única que
#       jarvis/roteamento_hierarquico/catalogo.py e a tela de perfis
#       já usam. ~1,5 mil tokens para o catálogo inteiro, o que cabe
#       com folga no teto de 8 mil tokens POR MINUTO do tier gratuito
#       da Groq (medido neste projeto).
#
#   True — a descrição COMPLETA da FunctionDeclaration de cada
#       ferramenta, com as ressalvas de uso e as travas de segurança
#       que o resumo não carrega. Escolhe melhor entre ferramentas
#       parecidas, e custa MUITO mais: o catálogo inteiro passa de 10
#       mil tokens, o que estoura o tier gratuito numa única chamada.
#       Só ligue isto com um plano pago ou um modelo local.
#
# Em qualquer um dos dois casos, a ferramenta RECOMENDADA volta para
# o cérebro com a descrição completa e todos os parâmetros — isto aqui
# decide só o que vai no catálogo de BUSCA, não o que volta na
# resposta.
def usar_catalogo_completo():
    return _ler_bool("AGENTE_FERRAMENTAS_CATALOGO_COMPLETO", False)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os
# campos automaticamente. Ver docs/INTEGRATION.md, seção "Tela de
# configurações".
def config_schema():
    return [
        {
            "nome": "AGENTE_FERRAMENTAS_MODELO",
            "rotulo": (
                "Modelo do sub-agente de ferramentas na Groq "
                "(padrão: openai/gpt-oss-20b)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
        {
            "nome": "AGENTE_FERRAMENTAS_CATALOGO_COMPLETO",
            "rotulo": (
                "Usar as descrições completas no catálogo de busca "
                "(true/false, padrão false — mais preciso, mas "
                "estoura o tier gratuito da Groq)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
