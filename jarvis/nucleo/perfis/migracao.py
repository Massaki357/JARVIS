# Garante que o perfil padrão — o jarvis completo, com todas as
# ferramentas e o prompt de sistema que o projeto sempre usou —
# existe em dados/perfis/completo/.
#
# O que essa migração fez, uma vez só
# ==================================
#
# O prompt de sistema morava em
# jarvis/nucleo/prompts/gemini_live_sistema.md. Ele FOI MOVIDO
# (git mv) para dados/perfis/completo/sistema.md, byte a byte igual, e
# jarvis/nucleo/prompts/__init__.py::instrucao_sistema_corpo() passou
# a lê-lo de lá.
#
# MOVIDO, não copiado, e isso é o ponto principal deste arquivo: não
# existe cópia congelada em lugar nenhum, e não existe mais nenhum
# arquivo no caminho antigo (conferido: sumiu do disco e do índice do
# Git). Há UM arquivo com esse texto no projeto inteiro, e é o
# sistema.md do perfil padrão. Editá-lo — pela tela de perfis ou
# direto no editor — muda o que a próxima chamada envia, porque o
# texto é lido do disco a cada início de chamada, nunca guardado em
# memória entre chamadas. Divergência silenciosa entre "o prompt do
# projeto" e "o prompt do perfil padrão" é impossível por construção,
# não por disciplina de quem edita.
#
# O bloco de autenticação (gemini_live_autenticacao.md) NÃO veio
# junto, de propósito: ele não pertence a perfil nenhum, é a trava de
# segurança que vale para todos os perfis, e continua em
# jarvis/nucleo/prompts/.
#
# Por que isso continua sendo código, e não só um arquivo commitado
# ================================================================
#
# A pasta de um perfil é dado em disco, e o usuário pode apagá-la.
# Esta função roda barata na abertura da tela de perfis e:
#
# - não faz nada se dados/perfis/completo/ já estiver completo;
# - recria o perfil.json (metadados) se só ele estiver faltando;
# - se o sistema.md não existir, levanta um erro CLARO dizendo o que
#   restaurar. Deliberadamente NÃO existe um caminho de recuperação a
#   partir do arquivo antigo: ressuscitar em silêncio um
#   gemini_live_sistema.md esquecido numa branch antiga seria
#   exatamente a divergência silenciosa que mover o arquivo eliminou.
#   Um prompt de 32 mil caracteres não pode ser regenerado do nada, e
#   inventar um substituto calado seria pior que falhar.
from . import armazenamento


def garantir_perfil_padrao():
    """
    Garante dados/perfis/completo/ com os dois arquivos, e devolve o
    perfil padrão carregado.

    Idempotente: chamar várias vezes não reescreve nada que já esteja
    no lugar.
    """
    pasta = armazenamento.caminho_do_perfil(armazenamento.SLUG_PADRAO)

    arquivo_sistema = pasta / armazenamento.ARQUIVO_SISTEMA
    arquivo_perfil = pasta / armazenamento.ARQUIVO_PERFIL

    if arquivo_perfil.is_file() and arquivo_sistema.is_file():
        return armazenamento.carregar_perfil(
            armazenamento.SLUG_PADRAO
        )

    if not arquivo_sistema.is_file():
        raise FileNotFoundError(
            "O prompt de sistema do perfil padrão não foi encontrado "
            f"em {arquivo_sistema}. Restaure esse arquivo do "
            "repositório (git checkout dados/perfis/completo/"
            "sistema.md) — esse texto não tem como ser regenerado."
        )

    # O sistema.md está lá, só faltam os metadados: recria só eles,
    # sem tocar no texto do prompt.
    perfil = armazenamento.criar_perfil(
        nome=armazenamento.NOME_PADRAO,
        prompt_sistema=arquivo_sistema.read_text(encoding="utf-8"),
        # None = todas as ferramentas registradas, resolvidas na hora
        # do uso. Ver TODAS_AS_FERRAMENTAS em armazenamento.py: uma
        # lista explícita faria um pacote novo nascer desligado no
        # perfil padrão, em silêncio. É por isso que a lista de
        # ferramentas DESTE perfil é imutável — ver
        # ferramentas_editaveis() lá.
        ferramentas=armazenamento.TODAS_AS_FERRAMENTAS,
        descricao=(
            "O jarvis completo: todas as ferramentas registradas e o "
            "prompt de sistema original do projeto."
        ),
        slug=armazenamento.SLUG_PADRAO,
        padrao=True,
    )

    print(
        f"[perfis] Metadados do perfil padrão recriados em {pasta}."
    )

    return perfil
