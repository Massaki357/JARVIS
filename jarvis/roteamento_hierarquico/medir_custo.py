# Script de medição do roteamento hierárquico (requisito 6 do
# pedido original, mais a instrumentação de cache de prompt pedida
# depois): compara, com chamadas REAIS à Groq (precisa de
# GROQ_API_KEY configurada no .env), o custo em tokens e a latência
# de três cenários:
#
#   (a) uma frase sem nenhuma ferramenta, chamada duas vezes em
#       sequência — só a etapa 1, e a comparação entre a 1ª chamada
#       (cache frio esperado) e a 2ª (cache potencialmente já
#       "esquentado", já que o prefixo do catálogo é idêntico);
#   (b) uma frase que precisa de ferramenta — etapa 1 + etapa 2
#       do roteador de verdade, somadas;
#   (c) a MESMA frase de (b), mas montando o schema completo das 45
#       ferramentas de pacote de uma vez só — o cenário monolítico
#       original, pra comparação direta com os 7.511 tokens já
#       medidos manualmente antes deste módulo existir.
#
# Cache de prompt: a Groq devolve (quando o modelo/conta suporta)
# usage.prompt_tokens_details.cached_tokens — a parte do prompt que
# bateu no cache automático, cobrada com 50% de desconto. Este script
# só LÊ e mostra esse número, nunca assume que o cache funcionou: se
# o campo não vier na resposta, ou vier zerado mesmo na 2ª chamada,
# isso é impresso como resultado, não escondido nem arredondado pra
# "funcionou mesmo assim".
#
# Rodar com: python -m jarvis.roteamento_hierarquico.medir_custo
import time

from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS

from . import catalogo
from . import config
from . import esquema_groq
from . import roteador

# Frases de exemplo. A segunda foi escolhida por apontar claramente
# pra uma única categoria (controle_apps) — o objetivo aqui é medir
# custo, não testar a resolução de ambiguidade (isso é melhor
# verificado manualmente com uma frase cruzada, à parte).
FRASE_SEM_FERRAMENTA = "Bom dia"
FRASE_COM_FERRAMENTA = "Abre o Spotify pra mim"

# Intervalo entre a 1ª e a 2ª chamada do cenário (a) — curto o
# suficiente pra não atrasar o script, mas dando um instante real
# pro cache da Groq (se existir pra esta conta/modelo) ter chance de
# já estar quente na 2ª chamada.
INTERVALO_ENTRE_CHAMADAS_SEGUNDOS = 2

# Medição manual anterior a este módulo existir, documentada no
# CLAUDE.md — mantida aqui como referência fixa de comparação, já
# que a chamada monolítica ao vivo (cenário c) pode falhar por rate
# limit (como já aconteceu num teste anterior) sem que isso invalide
# a comparação.
TOKENS_HISTORICO_SEM_ROTEAMENTO = 7511


# Lê usage.prompt_tokens_details.cached_tokens de forma defensiva.
# Devolve None se o campo simplesmente não veio na resposta (a
# Groq/o modelo pode não suportar ou não reportar isso) — DIFERENTE
# de devolver 0, que significa "veio, e não teve cache hit". Nunca
# confundir os dois casos: requisito 3 pede pra deixar o número real
# falar, não assumir.
def _tokens_cacheados(usage):
    detalhes = usage.get("prompt_tokens_details")

    if not isinstance(detalhes, dict) or "cached_tokens" not in detalhes:
        return None

    return detalhes.get("cached_tokens") or 0


def _descricao_cache(usage):
    cache = _tokens_cacheados(usage)

    if cache is None:
        return "campo de cache não veio na resposta da Groq"

    if cache == 0:
        return "0 tokens do cache (cache miss)"

    return f"{cache} tokens do cache (cache hit)"


# Custo efetivo estimado com o desconto de 50% já aplicado à parte
# cacheada. Devolve (custo_efetivo, teve_cache) — teve_cache=False
# quando o campo não veio ou veio zerado, e nesse caso custo_efetivo
# é simplesmente o total bruto (sem desconto nenhum pra aplicar).
def _custo_efetivo(usage):
    total = usage.get("total_tokens", 0)
    cache = _tokens_cacheados(usage)

    if not cache:
        return total, False

    return total - (cache * 0.5), True


def _custo_efetivo_turno(resultado):
    total_efetivo = 0.0
    teve_cache = False

    for etapa in resultado.etapas:
        efetivo, teve = _custo_efetivo(etapa.usage)
        total_efetivo += efetivo
        teve_cache = teve_cache or teve

    return total_efetivo, teve_cache


def _imprimir_etapa(etapa, prefixo="    "):
    usage = etapa.usage

    print(
        f"{prefixo}etapa {etapa.numero} ({etapa.modelo}): "
        f"{usage.get('prompt_tokens', '?')} prompt + "
        f"{usage.get('completion_tokens', '?')} completion = "
        f"{usage.get('total_tokens', '?')} tokens — "
        f"{etapa.latencia_segundos:.2f}s — {_descricao_cache(usage)}"
    )


# Cenário (a): a mesma frase sem ferramenta, duas vezes em sequência,
# pra comparar tokens cacheados entre a 1ª chamada (cache frio
# esperado) e a 2ª (cache potencialmente já quente, mesmo prefixo).
def medir_sem_ferramenta():
    print(f"\n(a) Sem ferramenta, duas chamadas em sequência: {FRASE_SEM_FERRAMENTA!r}")

    print("  chamada 1 (cache frio esperado):")
    resultado_1 = roteador.processar_turno(FRASE_SEM_FERRAMENTA)

    for etapa in resultado_1.etapas:
        _imprimir_etapa(etapa)

    print(f"    total: {resultado_1.total_tokens()} tokens")

    time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)

    print(
        f"  chamada 2 (cache potencialmente quente, "
        f"{INTERVALO_ENTRE_CHAMADAS_SEGUNDOS}s depois):"
    )
    resultado_2 = roteador.processar_turno(FRASE_SEM_FERRAMENTA)

    for etapa in resultado_2.etapas:
        _imprimir_etapa(etapa)

    print(f"    total: {resultado_2.total_tokens()} tokens")

    cache_1 = (
        _tokens_cacheados(resultado_1.etapas[0].usage)
        if resultado_1.etapas
        else None
    )
    cache_2 = (
        _tokens_cacheados(resultado_2.etapas[0].usage)
        if resultado_2.etapas
        else None
    )

    print("  diferença de cache entre a 1ª e a 2ª chamada:")

    if cache_1 is None or cache_2 is None:
        print(
            "    a Groq não devolveu o campo de tokens cacheados "
            "nesta conta/modelo — não dá pra afirmar que o cache "
            "funcionou."
        )
    elif cache_1 == 0 and cache_2 == 0:
        print(
            "    0 tokens cacheados nas duas chamadas — sem cache "
            "hit neste teste (não assumir que o cache funcionou só "
            "porque o prefixo é fixo)."
        )
    elif cache_2 > cache_1:
        print(
            f"    {cache_1} -> {cache_2} tokens cacheados: cache "
            "aparentemente esquentou entre a 1ª e a 2ª chamada."
        )
    else:
        print(
            f"    {cache_1} -> {cache_2} tokens cacheados: sem "
            "esquentamento visível entre as duas chamadas."
        )

    # A 2ª chamada é a mais representativa de uso contínuo (é o que
    # um usuário real veria na maioria dos turnos) — é ela que entra
    # no resumo final.
    return resultado_2


def medir_com_ferramenta():
    print(f"\n(b) Com ferramenta (roteado): {FRASE_COM_FERRAMENTA!r}")

    resultado = roteador.processar_turno(FRASE_COM_FERRAMENTA)

    for etapa in resultado.etapas:
        _imprimir_etapa(etapa)

    print(f"    total: {resultado.total_tokens()} tokens")
    print(f"    usou ferramenta: {resultado.usou_ferramenta}")

    if resultado.usou_ferramenta:
        print(f"    ferramenta executada: {resultado.ferramenta_executada}")

    print(f"    resposta: {resultado.resposta!r}")

    return resultado


def medir_cenario_monolitico():
    print(
        "\n(c) Mesma frase, schema completo das 45 ferramentas de "
        f"uma vez só (cenário original): {FRASE_COM_FERRAMENTA!r}"
    )

    schemas = esquema_groq.obter_todos_os_schemas(PACOTES_REGISTRADOS)

    mensagens = [
        {"role": "user", "content": FRASE_COM_FERRAMENTA},
    ]

    # Reaproveita o helper de baixo nível do próprio roteador — são o
    # mesmo módulo/pacote, não uma dependência externa.
    sucesso, dados, latencia = roteador._chamar_groq(
        mensagens,
        config.MODELO_GROQ_ETAPA1,
        tools=schemas,
        tool_choice="auto",
    )

    if not sucesso:
        print(f"    falhou: {dados}")

        return None

    usage = dados.get("usage", {})

    print(f"    {len(schemas)} ferramentas no schema")
    print(
        f"    {usage.get('prompt_tokens', '?')} prompt + "
        f"{usage.get('completion_tokens', '?')} completion = "
        f"{usage.get('total_tokens', '?')} tokens — {latencia:.2f}s — "
        f"{_descricao_cache(usage)}"
    )

    return usage


def main():
    if not config.GROQ_API_KEY:
        print("GROQ_API_KEY não configurada no .env — abortando.")

        return

    if not catalogo.verificar_catalogo_atualizado(PACOTES_REGISTRADOS):
        print(
            "(catálogo curto desatualizado em relação aos pacotes "
            "registrados — ver aviso acima; a medição continua "
            "mesmo assim)"
        )

    sem_ferramenta = medir_sem_ferramenta()
    com_ferramenta = medir_com_ferramenta()
    usage_monolitico = medir_cenario_monolitico()

    efetivo_sem, cache_sem = _custo_efetivo_turno(sem_ferramenta)
    efetivo_com, cache_com = _custo_efetivo_turno(com_ferramenta)

    print("\n--- resumo ---")

    print(
        f"sem ferramenta (2ª chamada):  {sem_ferramenta.total_tokens()} "
        "tokens brutos"
        + (
            f" (~{efetivo_sem:.1f} efetivos com desconto de cache)"
            if cache_sem
            else " (sem cache hit — nenhum desconto a aplicar)"
        )
    )

    print(
        f"com ferramenta (roteado):    {com_ferramenta.total_tokens()} "
        "tokens brutos"
        + (
            f" (~{efetivo_com:.1f} efetivos com desconto de cache)"
            if cache_com
            else " (sem cache hit — nenhum desconto a aplicar)"
        )
    )

    if usage_monolitico is not None:
        total_mono = usage_monolitico.get("total_tokens", "?")
        efetivo_mono, cache_mono = _custo_efetivo(usage_monolitico)

        print(
            f"com ferramenta (monolítico, medido agora): {total_mono} "
            "tokens brutos"
            + (
                f" (~{efetivo_mono:.1f} efetivos com desconto de cache)"
                if cache_mono
                else " (sem cache hit — nenhum desconto a aplicar)"
            )
        )
    else:
        print(
            "com ferramenta (monolítico, medido agora): falhou nesta "
            "execução (ver erro acima)"
        )

    print(
        "com ferramenta (monolítico, medição histórica anterior a "
        f"este módulo): {TOKENS_HISTORICO_SEM_ROTEAMENTO} tokens "
        "(referência fixa, sem cache, sem roteamento)"
    )


if __name__ == "__main__":
    main()
