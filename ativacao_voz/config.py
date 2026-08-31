# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# core/config.py de propósito, mesmo padrão de rede_jarvis/config.py e
# admin_terminal/config.py (cada pacote isolado lê o .env sozinho).
from dotenv import load_dotenv

import os

load_dotenv()

# Palavra (ou frase curta) que, reconhecida sozinha enquanto nenhuma
# chamada está ativa, inicia a chamada automaticamente. Não precisa
# ser uma palavra-chave especial nem exige nenhum cadastro/arquivo —
# ver ativacao_voz/detector.py, que usa reconhecimento de voz
# genérico (Vosk, 100% local, sem chave de API) e simplesmente
# compara o texto reconhecido com este valor.
#
# Padrão "iniciar chamada" — NÃO "jarvis" (o nome do assistente).
# Confirmado ao vivo, com o Vosk model.vosk_model_find_word(), que o
# modelo "small" em português usado aqui simplesmente não tem
# "jarvis" no vocabulário (nome de origem inglesa) — o reconhecedor
# NUNCA consegue transcrever essa palavra, nem em modo de gramática
# restrita (o próprio Vosk avisa "Ignoring word missing in
# vocabulary"), então qualquer valor default aqui precisa ser uma
# palavra ou frase que exista de fato nesse vocabulário. "iniciar" e
# "chamada" foram confirmados presentes antes de virar o padrão.
NOME_ATIVACAO = os.getenv(
    "NOME_ATIVACAO",
    "iniciar chamada",
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (configuracoes/window.py) montar os campos
# automaticamente — mesmo padrão dos demais pacotes com config_schema().
def config_schema():
    return [
        {
            "nome": "NOME_ATIVACAO",
            "rotulo": (
                "Frase de ativação por voz (padrão: \"iniciar "
                "chamada\" — precisa ser uma palavra/frase real do "
                "vocabulário do modelo Vosk em português)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
