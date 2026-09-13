from . import armazenamento


def garantir_perfil_padrao():
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

    perfil = armazenamento.criar_perfil(
        nome=armazenamento.NOME_PADRAO,
        prompt_sistema=arquivo_sistema.read_text(encoding="utf-8"),
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
