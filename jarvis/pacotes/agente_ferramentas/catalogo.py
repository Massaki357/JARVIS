"""
O catálogo que o sub-agente lê: NOME + DESCRIÇÃO de cada ferramenta,
mais os parâmetros exatos de cada uma.

NÃO É UMA LISTA NOVA. Este projeto já tem três lugares que sabem
quais ferramentas existem, e escrever um quarto seria garantir que um
deles envelheça em silêncio. Tudo aqui é DERIVADO:

  - quais ferramentas existem, e o resumo de uma linha de cada uma:
    jarvis/nucleo/perfis/catalogo_ferramentas.catalogo_completo(),
    que por sua vez deriva os nomes de PACOTES_REGISTRADOS e
    reaproveita os resumos de jarvis/roteamento_hierarquico/
    catalogo.py;
  - a descrição COMPLETA e os PARÂMETROS de cada ferramenta de
    pacote: a própria types.FunctionDeclaration que o pacote já
    expõe em obter_function_declarations() — a mesma que o cérebro
    recebe. É a fonte mais autoritativa que existe, e é ela que
    permite responder "como executar" sem ninguém redigitar nada.

Um pacote novo aparece aqui sozinho, com a descrição e os parâmetros
certos, no instante em que entra em PACOTES_REGISTRADOS.

FERRAMENTAS NATIVAS entram no catálogo (o cérebro pode muito bem
precisar de analisar_tela, que é nativa), mas só com nome e resumo:
as declarações nativas do Gemini vivem dentro de um método de
GeminiLiveWorker, inalcançáveis sem uma sessão viva. Isso não é um
buraco na prática — o cérebro JÁ TEM a declaração nativa completa na
própria sessão; o que faltava a ele era saber QUAL ferramenta usar, e
isso o catálogo responde.

IMPORTS ADIADOS, sempre. Este módulo pertence a um pacote que está
dentro de PACOTES_REGISTRADOS: importar o registro no topo do arquivo
fecha um ciclo (registro -> agente_ferramentas -> registro) e o app
não sobe.
"""

# As tools DESTE pacote. NUNCA entram no catálogo: um sub-agente que
# pode recomendar a si mesmo manda o cérebro consultá-lo de novo e o
# turno vira laço; e recomendar executar_ferramenta seria mandar
# executar "executar" sem dizer o quê.
TOOLS_PROPRIAS = (
    "buscar_ferramenta",
    "executar_ferramenta",
    "ler_instrucao_ferramenta",
)

ORIGEM_PACOTE = "pacote"
ORIGEM_NATIVA = "nativa"


def _declaracoes_de_pacote():
    """
    nome -> dict cru da FunctionDeclaration, de todos os pacotes
    registrados. Um pacote que falhe ao declarar suas tools é pulado,
    nunca derruba o catálogo inteiro.
    """
    from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS
    from jarvis.servicos.agentes.ferramentas import normalizar_esquema

    por_nome = {}

    for pacote in PACOTES_REGISTRADOS:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            try:
                bruto = declaracao.to_json_dict()

            except Exception:
                continue

            nome = bruto.get("name")

            if not nome or nome in TOOLS_PROPRIAS:
                continue

            parametros = bruto.get("parameters") or {}

            por_nome[nome] = {
                "descricao": (bruto.get("description") or "").strip(),
                "parametros": normalizar_esquema(parametros),
            }

    return por_nome


def _nomes_permitidos():
    """
    Os nomes que o CÉREBRO ATUAL realmente tem à mão: o perfil ativo
    intersectado com as ferramentas que existem no cérebro em uso.

    Recomendar uma ferramenta que o cérebro não tem declarada seria
    mandá-lo chamar algo inexistente — o perfil pode tê-la desligado,
    e o OpenAI Realtime tem 4 nativas contra as 16 do Gemini.

    Devolve None quando não dá para saber (perfil corrompido, disco
    fora do ar). None significa "não filtra nada": um catálogo
    completo demais é muito melhor do que um catálogo vazio, que
    deixaria o sub-agente sem nenhuma resposta possível.

    RESSALVA CONHECIDA: lê o perfil ativo AGORA, e trocar de perfil só
    vale a partir da próxima chamada. Se o usuário trocar no meio de
    uma chamada, este filtro passa a usar o perfil novo enquanto o
    cérebro ainda roda com o antigo. A consequência é recomendar uma
    ferramenta que o cérebro não encontra — exatamente o mesmo
    resultado de não filtrar nada, que é o comportamento de fallback.
    """
    try:
        from jarvis.nucleo import perfis
        from jarvis.nucleo.perfis import catalogo_ferramentas

        do_perfil = set(
            perfis.ferramentas_efetivas(perfis.perfil_ativo())
        )

        do_cerebro = set(
            catalogo_ferramentas.nomes_do_cerebro(
                catalogo_ferramentas.cerebro_atual_usa_openai()
            )
        )

        permitidos = do_perfil & do_cerebro

        return permitidos or None

    except Exception as erro:
        print(
            "[agente_ferramentas] Não consegui resolver as ferramentas "
            f"do perfil ativo; usando o catálogo inteiro. ({erro})"
        )

        return None


def montar():
    """
    A lista de ferramentas que o sub-agente enxerga nesta chamada.

    Cada item:

        {
          "nome": "descrever_tela",
          "resumo": "Descreve o que está aparecendo na tela...",
          "descricao": "<descrição completa da FunctionDeclaration>",
          "parametros": {"type": "object", "properties": {...}},
          "origem": "pacote" | "nativa",
          "categoria": "Visão e câmera",
          "oculta": True,   # não está no prefixo do cérebro
        }

    Ferramentas nativas vêm com "descricao" igual ao resumo e
    "parametros" vazio — ver o cabeçalho deste arquivo.

    Construído a cada chamada, de propósito: o perfil ativo e o
    cérebro em uso podem ter mudado desde a última, e um catálogo
    cacheado recomendaria ferramentas de um cenário que não vale
    mais. São dois dicionários em memória, não uma chamada de rede.
    """
    from jarvis.nucleo.perfis import catalogo_ferramentas
    from jarvis.nucleo.registro_pacotes import ferramentas_ocultas

    declaracoes = _declaracoes_de_pacote()
    permitidos = _nomes_permitidos()

    # Quais NÃO estão no prefixo do cérebro. Decide a instrução final:
    # uma ferramenta declarada ele chama direto; uma oculta ele chama
    # por executar_ferramenta. Mandar o caminho errado custa um turno
    # inteiro de ida e volta à toa.
    try:
        ocultas = ferramentas_ocultas()

    except Exception:
        ocultas = set()

    itens = []

    for item in catalogo_ferramentas.catalogo_completo():
        nome = item["nome"]

        if nome in TOOLS_PROPRIAS:
            continue

        if permitidos is not None and nome not in permitidos:
            continue

        # SÓ AS OCULTAS. O cérebro consulta a própria lista de
        # ferramentas diretas ANTES de chamar o sub-agente, e só chega
        # aqui quando nenhuma delas serve — oferecer as diretas de novo
        # neste catálogo seria cobrar duas vezes pela mesma busca e
        # engordar o prompt da Groq à toa.
        #
        # Exceção: sem nenhuma oculta (FERRAMENTAS_SOB_DEMANDA=false),
        # o catálogo inteiro continua valendo, senão buscar_ferramenta
        # ficaria sem resposta possível nesse modo.
        if ocultas and nome not in ocultas:
            continue

        resumo = item["resumo"]
        completa = declaracoes.get(nome)

        itens.append(
            {
                "nome": nome,
                "resumo": resumo,
                "descricao": (
                    completa["descricao"] if completa else resumo
                ),
                "parametros": (
                    completa["parametros"] if completa else {}
                ),
                "origem": (
                    ORIGEM_PACOTE if completa else ORIGEM_NATIVA
                ),
                "categoria": item["rotulo_categoria"],
                "oculta": nome in ocultas,
            }
        )

    return itens


def texto_para_prompt(itens, usar_descricao_completa=False):
    """
    O catálogo como texto, agrupado por categoria — é isto que vai
    dentro do prompt do sub-agente.

    usar_descricao_completa troca o resumo de uma linha pela descrição
    inteira da FunctionDeclaration. Escolhe melhor entre ferramentas
    parecidas e custa muito mais token; ver
    config.usar_catalogo_completo() para a conta.
    """
    por_categoria = {}

    for item in itens:
        por_categoria.setdefault(item["categoria"], []).append(item)

    blocos = []

    for categoria, ferramentas in por_categoria.items():
        linhas = [f"## {categoria}"]

        for ferramenta in ferramentas:
            descricao = (
                ferramenta["descricao"]
                if usar_descricao_completa
                else ferramenta["resumo"]
            )

            # Numa linha só: uma descrição completa tem quebras de
            # linha próprias, e elas fariam o item seguinte parecer
            # uma ferramenta nova para quem está lendo o catálogo.
            descricao = " ".join(str(descricao).split())

            linhas.append(f"- {ferramenta['nome']}: {descricao}")

        blocos.append("\n".join(linhas))

    return "\n\n".join(blocos)


def procurar(itens, nome):
    """O item de `nome`, ou None. Comparação exata, nunca aproximada."""
    for item in itens:
        if item["nome"] == nome:
            return item

    return None
