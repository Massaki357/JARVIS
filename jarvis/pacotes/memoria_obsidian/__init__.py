# Memória do jarvis em um vault do Obsidian.
#
# Substitui o sistema antigo (dados/memoria.json — frases curtas, no
# máximo 50, todas injetadas no prompt a cada sessão) por uma pasta de
# arquivos .md ligados entre si com [[links]]. O app do Obsidian não
# precisa estar instalado nem aberto: o jarvis só escreve e lê
# arquivos de texto. Abrir a pasta no Obsidian depois é opcional, e aí
# os links já estão lá funcionando.
#
# A diferença de fundo em relação ao sistema antigo não é o formato, é
# COMO a memória chega ao modelo: antes tudo era pré-carregado no
# prompt; agora entra só um contexto inicial pequeno, e o modelo busca
# o resto sob demanda com buscar_memorias_relacionadas. É o que
# permite a memória crescer sem inchar o prompt.
#
# Módulos:
#   config.py        pasta do vault, critérios de poda, .env
#   notas.py         ler/escrever .md, frontmatter, segurança de caminho
#   escritor.py      salvar/atualizar nota, links automáticos, fixar
#   busca.py         busca por palavra-chave + notas ligadas
#   esquecer.py      apagar uma nota (com a recusa a apagar tudo)
#   consolidacao.py  poda, arquivamento e resumo periódico
#   migracao.py      script manual, roda uma vez (ver o arquivo)
#
# Ver docs/INTEGRATION.md, seção "memoria_obsidian".
from google.genai import types

from . import busca, config, consolidacao, escritor, esquecer, notas

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="salvar_memoria",
        description=(
            "Guarda de forma permanente uma informação que o usuário "
            "pediu explicitamente para lembrar. Use SOMENTE quando "
            "ele disser claramente para lembrar, guardar ou anotar "
            "algo — nunca por iniciativa própria, nunca para guardar "
            "algo que ele só mencionou de passagem, e nunca para "
            "registrar conclusões suas sobre ele. O título deve ser "
            "curto e descritivo (ex: 'Email do Gabriel'), porque é "
            "por ele que a memória será encontrada depois. Se o "
            "usuário deixar claro que aquilo é importante e não pode "
            "ser esquecido nunca, passe fixar=true."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "titulo": types.Schema(
                    type="STRING",
                    description=(
                        "Título curto e descritivo da memória."
                    ),
                ),
                "conteudo": types.Schema(
                    type="STRING",
                    description=(
                        "A informação a guardar, em uma ou duas "
                        "frases objetivas."
                    ),
                ),
                "fixar": types.Schema(
                    type="BOOLEAN",
                    description=(
                        "true somente quando o usuário disser que "
                        "aquilo nunca pode ser esquecido."
                    ),
                ),
            },
            required=["titulo", "conteudo"],
        ),
    ),
    types.FunctionDeclaration(
        name="buscar_memorias_relacionadas",
        description=(
            "Procura na memória o que você já sabe sobre um assunto. "
            "Use sempre que a conversa tocar em algo pessoal do "
            "usuário (uma pessoa, um projeto, uma preferência, um "
            "contato) e você não tiver aquilo no contexto inicial da "
            "sessão — em vez de dizer que não lembra, procure "
            "primeiro. A busca devolve também os títulos das notas "
            "ligadas às encontradas; se algum parecer útil, busque "
            "por ele em seguida. Não invente lembranças: se a busca "
            "não devolver nada, diga que não tem isso guardado."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "consulta": types.Schema(
                    type="STRING",
                    description=(
                        "Assunto ou palavras-chave a procurar."
                    ),
                ),
            },
            required=["consulta"],
        ),
    ),
    types.FunctionDeclaration(
        name="esquecer_memoria",
        description=(
            "Apaga uma memória guardada, pelo título. Use somente "
            "quando o usuário pedir claramente para esquecer algo "
            "específico. Se a função devolver mais de uma memória "
            "parecida, pergunte ao usuário qual delas antes de "
            "tentar de novo — nunca escolha sozinho."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "titulo": types.Schema(
                    type="STRING",
                    description=(
                        "Título ou trecho do título da memória."
                    ),
                ),
            },
            required=["titulo"],
        ),
    ),
    types.FunctionDeclaration(
        name="listar_memorias",
        description=(
            "Lista os títulos do que você tem guardado. Use quando o "
            "usuário perguntar o que você lembra ou o que sabe sobre "
            "ele, sem citar um assunto específico. Para um assunto "
            "específico, use buscar_memorias_relacionadas."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={},
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def _listar_titulos():
    if not config.configurado():
        return (
            "A pasta do vault não está configurada. Peça para "
            "definir PASTA_VAULT_JARVIS no arquivo .env."
        )

    todas = notas.listar_notas()

    if not todas:
        return "Ainda não tenho nenhuma memória guardada."

    todas.sort(
        key=lambda nota: str(
            nota["frontmatter"].get("last_used", "")
        ),
        reverse=True,
    )

    titulos = ", ".join(nota["titulo"] for nota in todas[:30])

    resto = (
        f" (e mais {len(todas) - 30})" if len(todas) > 30 else ""
    )

    return (
        f"Tenho {len(todas)} memórias guardadas: {titulos}{resto}. "
        "Se o usuário quiser detalhes de alguma, use "
        "buscar_memorias_relacionadas."
    )


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "salvar_memoria":
        return escritor.salvar_memoria(
            argumentos.get("titulo", ""),
            argumentos.get("conteudo", ""),
            fixar=bool(argumentos.get("fixar", False)),
        )

    if nome_funcao == "buscar_memorias_relacionadas":
        return busca.buscar_e_formatar(
            argumentos.get("consulta", "")
        )

    if nome_funcao == "esquecer_memoria":
        return esquecer.esquecer_memoria(
            argumentos.get("titulo", "")
        )

    if nome_funcao == "listar_memorias":
        return _listar_titulos()

    return None


# Contexto inicial leve da sessão: só as notas mais recentes, não
# tudo. Chamado por jarvis/gemini/cliente_live.py ao montar a
# instrucao_sistema.
def contexto_inicial():
    return busca.contexto_inicial()


# Chamado uma vez na inicialização do app (main.py). Dispara, em
# thread de fundo, a varredura periódica de poda/consolidação se já
# fizer mais de INTERVALO_VARREDURA_DIAS desde a última.
def iniciar():
    if not config.configurado():
        print(
            "[MEMORIA] PASTA_VAULT_JARVIS não configurada — a "
            "memória em vault está desligada."
        )

        return False

    notas.garantir_pastas()

    return consolidacao.iniciar_varredura_periodica()
