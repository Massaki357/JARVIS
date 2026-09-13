from jarvis.servicos.agentes import ferramentas as conversor


def _despachar(nome, argumentos):
    from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS

    for pacote in PACOTES_REGISTRADOS:
        try:
            resultado = pacote.despachar(nome, argumentos)

        except Exception as erro:
            print(
                f"[agente_ferramentas] Erro ao executar '{nome}': {erro}"
            )

            return (
                f"A ferramenta {nome} falhou com um erro interno "
                f"({type(erro).__name__}). Nada foi executado."
            )

        if resultado is not None:
            return resultado

    return None


def executar(nome, argumentos):
    nome = str(nome or "").strip()

    if not nome:
        return (
            "Nenhum nome de ferramenta foi informado. Chame "
            "buscar_ferramenta primeiro para descobrir qual usar."
        )

    try:
        from jarvis.nucleo.registro_pacotes import ferramentas_ocultas

        ocultas = ferramentas_ocultas()

    except Exception as erro:
        return (
            "Não consegui resolver a lista de ferramentas executáveis "
            f"agora ({erro}). Nada foi executado."
        )

    # Nativas e especiais nunca por aqui: o worker precisa ver o nome delas.
    if nome not in ocultas:
        from jarvis.nucleo.perfis import catalogo_ferramentas

        try:
            existe = nome in catalogo_ferramentas.nomes_disponiveis()

        except Exception:
            existe = False

        if existe:
            return (
                f"A ferramenta {nome} você já tem declarada nesta "
                "sessão — chame ela DIRETO, com os parâmetros dela, em "
                "vez de passar por executar_ferramenta. Nada foi "
                "executado."
            )

        return (
            f"Não existe nenhuma ferramenta chamada {nome}. Chame "
            "buscar_ferramenta para descobrir o nome certo. Nada foi "
            "executado."
        )

    resultado = _despachar(
        nome, conversor.interpretar_argumentos(argumentos)
    )

    if resultado is None:
        return (
            f"A ferramenta {nome} não foi reconhecida por nenhum "
            "pacote registrado. Nada foi executado."
        )

    return resultado
