# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão de rede_jarvis, casa_inteligente e delegacao_ia (ver
# docs/INTEGRATION.md).
from google.genai import types

from . import acoes

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar(). Quatro
# tools de voz aqui — abrir_site, tocar_musica_youtube, pausar_musica,
# retomar_musica. fechar_navegador() existe em acoes.py mas
# deliberadamente NÃO é exposta como tool de voz (fora do escopo
# pedido) — fica disponível pra uso futuro/interno.
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_site",
        description=(
            "Abre um site de verdade no navegador controlado pelo "
            "jarvis — diferente de abrir_app_local (que abre "
            "programas instalados do Windows), isto abre uma página "
            "web real, permitindo outras ações nela depois (como "
            "tocar_musica_youtube). Use quando o usuário pedir pra "
            "abrir um site específico ou pesquisar algo no navegador "
            "(ex: 'abre o youtube', 'abre o site da globo', "
            "'pesquisa receita de bolo no navegador'). Se o texto "
            "parecer um endereço de site (ex: 'google.com', "
            "'mercadolivre.com.br'), abre direto nele; caso "
            "contrário, faz uma busca no Google com o termo exato "
            "que o usuário disse."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "url_ou_termo": types.Schema(
                    type="STRING",
                    description=(
                        "O site (ex: 'youtube.com') ou o termo de "
                        "busca, exatamente como o usuário falou."
                    ),
                ),
            },
            required=[
                "url_ou_termo",
            ],
        ),
    ),

    types.FunctionDeclaration(
        name="tocar_musica_youtube",
        description=(
            "Busca uma música ou vídeo no YouTube e toca o primeiro "
            "resultado, no navegador controlado pelo jarvis. Use "
            "quando o usuário pedir explicitamente pra tocar/colocar "
            "uma música ou vídeo específico no YouTube (ex: 'toca a "
            "música X no youtube', 'coloca aquele vídeo do Y', "
            "'bota uma playlist de lofi'). Depois de chamar esta "
            "função com sucesso, a música já está tocando — não "
            "chame pausar_musica nem retomar_musica em seguida."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "consulta": types.Schema(
                    type="STRING",
                    description=(
                        "O nome da música, artista ou vídeo a "
                        "buscar, exatamente como o usuário pediu."
                    ),
                ),
            },
            required=[
                "consulta",
            ],
        ),
    ),

    types.FunctionDeclaration(
        name="pausar_musica",
        description=(
            "Pausa a música ou vídeo que está tocando no YouTube, na "
            "mesma aba aberta por tocar_musica_youtube. Use quando o "
            "usuário pedir claramente pra pausar, parar ou silenciar "
            "a música (ex: 'pausa a música', 'para o vídeo'). Se não "
            "houver nada tocando, a função avisa isso — não invente "
            "que pausou algo que não existia."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={},
            required=[],
        ),
    ),

    types.FunctionDeclaration(
        name="retomar_musica",
        description=(
            "Retoma (despausa) a música ou vídeo pausado no YouTube, "
            "na mesma aba. Use quando o usuário pedir pra continuar, "
            "retomar, despausar ou voltar a tocar a música (ex: "
            "'continua a música', 'despausa'). Se não houver nada "
            "pausado, a função avisa isso."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={},
            required=[],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "abrir_site":
        return acoes.abrir_site(
            argumentos.get("url_ou_termo", "")
        )

    if nome_funcao == "tocar_musica_youtube":
        return acoes.tocar_musica_youtube(
            argumentos.get("consulta", "")
        )

    if nome_funcao == "pausar_musica":
        return acoes.pausar_musica()

    if nome_funcao == "retomar_musica":
        return acoes.retomar_musica()

    return None
