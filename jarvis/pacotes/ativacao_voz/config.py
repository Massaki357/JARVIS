# Carrega as variáveis de ambiente do arquivo .env — decoupled de
# jarvis/nucleo/config.py de propósito, mesmo padrão de jarvis/pacotes/rede_jarvis/config.py e
# jarvis/pacotes/admin_terminal/config.py (cada pacote isolado lê o .env sozinho).
from dotenv import load_dotenv

import os

load_dotenv()

# Palavra (ou frase curta) que, reconhecida sozinha enquanto nenhuma
# chamada está ativa, inicia a chamada automaticamente. Não precisa
# ser uma palavra-chave especial nem exige nenhum cadastro/arquivo —
# ver jarvis/pacotes/ativacao_voz/detector.py, que usa reconhecimento de voz
# genérico (Vosk, 100% local, sem chave de API) e simplesmente
# compara o texto reconhecido com este valor.
#
# Esta MESMA frase serve dois propósitos agora: (1) inicia uma
# chamada nova a partir do modo ocioso (como sempre foi) e (2) retoma
# uma chamada PAUSADA por voz (ver a tool pausar_chamada em
# jarvis/gemini/cliente_live.py / jarvis/openai_realtime/cliente_realtime.py) —
# o app não distingue os dois casos aqui, quem decide é
# MainWindow.iniciar_chamada_por_voz, que resume a conversa
# automaticamente sempre que já existir um session_handle guardado.
#
# Padrão "voltar chamada" — NÃO "jarvis" nem "alfred" (o nome do
# assistente, editável em NOME_JARVIS). Confirmado ao vivo, com o
# Vosk model.vosk_model_find_word(), que o modelo "small" em
# português usado aqui simplesmente não tem NENHUM dos dois no
# vocabulário (nomes de origem estrangeira) — o reconhecedor NUNCA
# consegue transcrever essas palavras, nem em modo de gramática
# restrita (o próprio Vosk avisa "Ignoring word missing in
# vocabulary"), então qualquer valor aqui precisa ser uma palavra ou
# frase que exista de fato nesse vocabulário — nunca o nome do
# assistente em si. "voltar" e "chamada" foram confirmados presentes
# antes de virar o padrão (o antigo padrão, "iniciar chamada", também
# funcionava pelo mesmo motivo, mas "voltar" combina melhor com o
# novo uso de retomar uma conversa pausada).
NOME_ATIVACAO = os.getenv(
    "NOME_ATIVACAO",
    "voltar chamada",
)


# Descreve as variáveis de .env deste pacote pra tela de
# configurações (jarvis/pacotes/configuracoes/window.py) montar os campos
# automaticamente — mesmo padrão dos demais pacotes com config_schema().
def config_schema():
    return [
        {
            "nome": "NOME_ATIVACAO",
            "rotulo": (
                "Frase de ativação por voz — inicia uma chamada nova "
                "OU retoma uma chamada pausada (padrão: \"voltar "
                "chamada\" — precisa ser uma palavra/frase real do "
                "vocabulário do modelo Vosk em português; nomes "
                "estrangeiros como o nome do assistente não "
                "funcionam)"
            ),
            "sensivel": False,
            "obrigatoria": False,
        },
    ]
