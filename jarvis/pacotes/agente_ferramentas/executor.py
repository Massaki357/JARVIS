"""
Executa uma ferramenta que o cérebro NÃO tem declarada na sessão.

É a segunda metade do par: buscar_ferramenta descobre qual é,
executar_ferramenta roda. Sem ela, esconder ferramenta do prefixo
seria só tirar a capacidade do assistente — o sub-agente diria "use
criar_arquivo" e o cérebro não teria como chamar.

O QUE ELA SE RECUSA A FAZER, e por quê
======================================

Só despacha o que está em registro_pacotes.ferramentas_ocultas(). Um
nome fora desse conjunto volta com uma instrução para o cérebro
chamá-lo DIRETO, e isso não é burocracia:

  - as NATIVAS (analisar_tela, preparar_email, encerrar_chamada...)
    não são despachadas por pacote nenhum — vivem dentro do worker e
    dependem da sessão viva. Despachar aqui devolveria "não
    reconhecida" no melhor caso;
  - as ESPECIAIS (descrever_tela, clicar_elemento_visual,
    rolar_pagina...) dependem de o worker VER O NOME DELAS na tool
    call para capturar a imagem, segurar o mutex visual ou silenciar
    o áudio do turno. Chamadas por aqui, o nome que chega ao worker é
    "executar_ferramenta" e os três comportamentos sumiriam em
    silêncio — o mesmo bug já documentado em
    jarvis/nucleo/registro_pacotes.py.

As duas continuam declaradas no cérebro exatamente para poderem ser
chamadas direto. A recusa aqui é a rede de segurança para quando o
modelo tentar o caminho errado.
"""

from jarvis.servicos.agentes import ferramentas as conversor


def _despachar(nome, argumentos):
    """
    O mesmo laço de PACOTES_REGISTRADOS que os dois workers usam: para
    no primeiro pacote que reconhece o nome. Devolve None se nenhum
    reconhecer.
    """
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
    """
    Roda `nome` com `argumentos` e devolve a string de resultado —
    exatamente a mesma que o cérebro receberia se tivesse chamado a
    ferramenta direto. Nunca levanta exceção.

    `argumentos` chega como STRING JSON, não como objeto. Os dois
    provedores lidam mal com um parâmetro de esquema aberto (um
    "object" sem properties declaradas), e uma string é o formato que
    funciona igual nos dois. interpretar_argumentos() já trata JSON
    inválido devolvendo dicionário vazio — aí a própria ferramenta
    responde qual parâmetro faltou, que é uma mensagem muito melhor do
    que "JSON malformado".
    """
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
        # O nome veio de ferramentas_ocultas(), que sai dos próprios
        # pacotes — chegar aqui significa que o registro mudou no meio
        # do caminho. Defensivo, não esperado.
        return (
            f"A ferramenta {nome} não foi reconhecida por nenhum "
            "pacote registrado. Nada foi executado."
        )

    return resultado
