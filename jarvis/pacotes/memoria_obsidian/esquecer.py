# Apagar uma memória do vault.
#
# Duas regras herdadas do sistema antigo
# (jarvis/servicos/memoria/gerenciador.py) que NÃO se perdem na
# migração:
#
#   1. Recusa a pedidos de apagar tudo de uma vez. É uma regra de
#      segurança, não uma limitação técnica.
#   2. Nunca apaga por adivinhação: se mais de uma nota casa com o
#      que foi pedido, devolve a lista para o jarvis perguntar qual,
#      em vez de escolher a primeira.
from . import config, notas

# Conjunto herdado do gerenciador antigo, ampliado com as variações
# que aparecem naturalmente ao falar.
COMANDOS_APAGAR_TUDO = {
    "tudo",
    "todas",
    "todos",
    "todas as memorias",
    "todas as notas",
    "apagar tudo",
    "apague tudo",
    "limpar tudo",
    "esquecer tudo",
    "esqueca tudo",
    "apagar todas",
    "apagar todas as memorias",
    "esquecer todas as memorias",
    "limpar a memoria",
    "zerar a memoria",
}


def esquecer_memoria(titulo):
    if not config.configurado():
        return (
            "A pasta do vault não está configurada. Peça para "
            "definir PASTA_VAULT_JARVIS no arquivo .env."
        )

    titulo = str(titulo or "").strip()

    if not titulo:
        return "Qual memória você quer que eu esqueça?"

    referencia = notas.normalizar(titulo)

    # Segurança contra exclusão em massa — mantida exatamente com o
    # mesmo espírito do sistema antigo.
    if referencia in COMANDOS_APAGAR_TUDO:
        return (
            "Por segurança, não apago todas as memórias em uma única "
            "solicitação. Peça para esquecer uma informação "
            "específica."
        )

    encontradas = notas.localizar_por_titulo(
        titulo,
        incluir_arquivo=True,
    )

    if not encontradas:
        return (
            f"Não encontrei nenhuma memória parecida com '{titulo}'. "
            "Nada foi apagado."
        )

    # Ambiguidade: devolve os candidatos e não apaga nada.
    if len(encontradas) > 1:
        nomes = ", ".join(n["titulo"] for n in encontradas[:5])

        return (
            f"Encontrei mais de uma memória parecida com '{titulo}': "
            f"{nomes}. Qual delas você quer que eu esqueça? Não "
            "apaguei nada ainda."
        )

    nota = encontradas[0]

    try:
        caminho = notas.caminho_seguro(nota["caminho"])
        caminho.unlink()

    except ValueError as erro:
        return f"Não consegui apagar essa memória: {erro}"

    except OSError as erro:
        return f"Não consegui apagar o arquivo da memória: {erro}"

    return f"Pronto, esqueci a memória '{nota['titulo']}'."
