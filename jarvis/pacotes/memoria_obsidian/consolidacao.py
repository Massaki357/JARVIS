# Poda, arquivamento e consolidação — o que impede o vault de crescer
# para sempre.
#
# O ciclo de vida de uma nota tem três estágios, e nenhum pula etapa:
#
#   ativa  -> arquivada  -> resumida (e só então o original some)
#
# Uma nota só é ARQUIVADA se os TRÊS critérios baterem juntos: sem uso
# há mais de DIAS_SEM_USO_PARA_PODAR, com menos de
# MAXIMO_ACESSOS_PARA_PODAR acessos, e não fixada. Arquivar é MOVER,
# nunca apagar — a nota continua inteira em arquivo/ e pode voltar.
#
# Um arquivo original só é APAGADO depois de ter entrado num resumo
# gravado com sucesso em disco. Se a geração do resumo falhar por
# qualquer motivo, nada é apagado. É a regra mais importante daqui.
import os
import threading
import time
from datetime import datetime, timedelta

# Instrução de resumo enviada ao Gemini na consolidação — centralizada
# em jarvis/nucleo/prompts/, seção MEMORIA_OBSIDIAN.
from jarvis.nucleo import prompts

from . import config, notas

# Evita duas varreduras simultâneas (ex: o app abrindo duas vezes
# rápido, ou uma varredura manual durante a automática).
_LOCK_VARREDURA = threading.Lock()

_thread_varredura = None


def _quantos_dias_desde(texto_data):
    if not texto_data:
        return None

    try:
        momento = datetime.fromisoformat(str(texto_data))

    except (TypeError, ValueError):
        return None

    return (datetime.now() - momento).days


# Os três critérios. Separado em função própria de propósito: é a
# regra que decide o destino de uma memória do usuário, então precisa
# ser lida de um lugar só e testada isoladamente.
def deve_podar(nota, agora=None):
    frontmatter = nota["frontmatter"]

    if bool(frontmatter.get("pinned", False)):
        return False

    try:
        acessos = int(frontmatter.get("access_count", 0))

    except (TypeError, ValueError):
        acessos = 0

    if acessos >= config.MAXIMO_ACESSOS_PARA_PODAR:
        return False

    dias = _quantos_dias_desde(frontmatter.get("last_used"))

    if dias is None:
        return False

    return dias > config.DIAS_SEM_USO_PARA_PODAR


# Move as notas que batem os três critérios para arquivo/. Devolve a
# lista de títulos arquivados.
def arquivar_notas_paradas():
    if not config.configurado():
        return []

    notas.garantir_pastas()

    arquivadas = []

    for nota in notas.listar_notas():
        if not deve_podar(nota):
            continue

        destino = config.pasta_arquivo() / nota["caminho"].name

        try:
            # Passa pelo caminho_seguro dos dois lados: nada entra nem
            # sai fora da pasta do vault.
            origem = notas.caminho_seguro(nota["caminho"])
            destino = notas.caminho_seguro(destino)

            if destino.exists():
                destino = notas.caminho_seguro(
                    destino.with_name(
                        f"{destino.stem}-{int(datetime.now().timestamp())}.md"
                    )
                )

            origem.replace(destino)
            arquivadas.append(nota["titulo"])

        except (ValueError, OSError) as erro:
            print(
                f"[MEMORIA] Não consegui arquivar '{nota['titulo']}': "
                f"{erro}"
            )

    return arquivadas


# Traz uma nota de volta do arquivo/ para a pasta ativa e zera o
# contador — ela "reativou" e sai do caminho de poda.
def reativar_nota(nota):
    try:
        origem = notas.caminho_seguro(nota["caminho"])
        destino = notas.caminho_seguro(
            config.PASTA_VAULT / origem.name
        )

        frontmatter = dict(nota["frontmatter"])
        frontmatter["last_used"] = notas.agora()
        frontmatter["access_count"] = 0

        notas.escrever_nota(destino, frontmatter, nota["corpo"])
        origem.unlink()

    except (ValueError, OSError) as erro:
        print(
            f"[MEMORIA] Não consegui reativar '{nota['titulo']}': "
            f"{erro}"
        )

        return False

    print(f"[MEMORIA] Nota reativada do arquivo: {nota['titulo']}")

    return True


# Procura, entre as notas arquivadas, alguma que case com a consulta —
# usada pela busca quando a pasta ativa não devolveu nada. Reativa as
# que baterem, para uma nota citada nunca ser consolidada logo em
# seguida.
def reativar_por_consulta(consulta):
    if not config.configurado():
        return []

    alvo = notas.normalizar(consulta)

    if len(alvo) < 3:
        return []

    reativadas = []

    for nota in notas.listar_notas(incluir_arquivo=True):
        texto = notas.normalizar(
            nota["titulo"] + " " + nota["corpo"]
        )

        if alvo in texto and reativar_nota(nota):
            reativadas.append(nota["titulo"])

    return reativadas


# Nome do resumo pelo período atual: resumo-2026-Q3.md
def _nome_resumo(momento=None):
    momento = momento or datetime.now()
    trimestre = (momento.month - 1) // 3 + 1

    return f"resumo-{momento.year}-Q{trimestre}.md"


# Pede ao Gemini um resumo condensado das notas arquivadas. Chamada de
# texto simples, sem voz e sem interface — nada a ver com a sessão
# Live. Devolve (sucesso, texto).
def _gerar_resumo(notas_arquivadas):
    # A chave é a mesma do resto do app; lida direto do ambiente
    # (config.py já chamou load_dotenv) para este pacote não depender
    # de jarvis/nucleo/config.py.
    chave = (os.getenv("GEMINI_API_KEY") or "").strip()

    if not chave:
        return False, "GEMINI_API_KEY não configurada."

    blocos = []

    for nota in notas_arquivadas:
        blocos.append(f"### {nota['titulo']}\n{nota['corpo']}")

    pedido = prompts.CONSOLIDACAO_RESUMO_ARQUIVO.format(
        blocos="\n\n".join(blocos)
    )

    # Tenta mais de uma vez com espera crescente. Erros temporários
    # (503 de modelo sobrecarregado, 429 de limite) aconteceram de
    # verdade no primeiro teste real desta função, e sem retentativa
    # eles significavam simplesmente pular a consolidação da semana.
    # Como isto roda numa thread de fundo, sem ninguém esperando,
    # esperar alguns segundos não custa nada.
    ultimo_erro = ""

    for tentativa in range(config.TENTATIVAS_CONSOLIDACAO):
        if tentativa:
            time.sleep(
                config.ESPERA_ENTRE_TENTATIVAS_SEGUNDOS * tentativa
            )

        try:
            from google import genai

            cliente = genai.Client(api_key=chave)

            resposta = cliente.models.generate_content(
                model=config.MODELO_CONSOLIDACAO,
                contents=pedido,
            )

            texto = (getattr(resposta, "text", "") or "").strip()

            if texto:
                return True, texto

            ultimo_erro = "O modelo devolveu um resumo vazio."

        except Exception as erro:
            ultimo_erro = f"Falha ao gerar o resumo: {erro}"

            print(
                f"[MEMORIA] Tentativa {tentativa + 1} de "
                f"{config.TENTATIVAS_CONSOLIDACAO} falhou: "
                f"{str(erro)[:120]}"
            )

    return False, ultimo_erro


# Consolida a pasta arquivo/ quando ela acumular notas suficientes.
#
# Ordem obrigatória, e é o ponto mais delicado do pacote: gera o
# resumo -> grava o resumo em disco -> só então apaga os originais, e
# apenas os que entraram nele. Qualquer falha antes disso encerra a
# operação sem apagar nada.
def consolidar_arquivo(forcar=False):
    if not config.configurado():
        return "A pasta do vault não está configurada."

    notas.garantir_pastas()

    arquivadas = [
        nota for nota in notas.listar_notas(incluir_arquivo=True)
        # O próprio resumo mora em arquivo/; nunca resumir um resumo.
        if not nota["titulo"].startswith("resumo-")
    ]

    if not forcar and len(arquivadas) < config.MINIMO_NOTAS_PARA_CONSOLIDAR:
        return (
            f"Ainda não há notas arquivadas suficientes para "
            f"consolidar ({len(arquivadas)} de "
            f"{config.MINIMO_NOTAS_PARA_CONSOLIDAR})."
        )

    if not arquivadas:
        return "Não há notas arquivadas para consolidar."

    sucesso, resumo = _gerar_resumo(arquivadas)

    if not sucesso:
        # NADA é apagado quando o resumo falha.
        print(f"[MEMORIA] Consolidação abortada: {resumo}")

        return (
            f"Não consegui gerar o resumo ({resumo}). Nenhuma nota "
            "foi apagada."
        )

    caminho_resumo = config.pasta_arquivo() / _nome_resumo()

    titulos = [nota["titulo"] for nota in arquivadas]

    corpo_resumo = (
        "Resumo condensado de "
        f"{len(arquivadas)} notas arquivadas, geradas em "
        f"{notas.agora()}.\n\n"
        f"{resumo}\n\n"
        "### Notas originais resumidas\n"
        + "\n".join(f"- {titulo}" for titulo in titulos)
    )

    # Se já existir um resumo do mesmo período, o novo texto é
    # acrescentado ao que já estava lá, nunca sobrescreve.
    existente = notas.ler_nota(caminho_resumo)

    if existente is not None:
        corpo_resumo = (
            existente["corpo"].strip()
            + "\n\n---\n\n"
            + corpo_resumo
        )

    frontmatter = {
        "created": notas.agora(),
        "last_used": notas.agora(),
        "access_count": 0,
        # Um resumo nunca é podado nem consolidado de novo.
        "pinned": True,
    }

    try:
        notas.escrever_nota(
            caminho_resumo,
            frontmatter,
            corpo_resumo,
        )

    except (ValueError, OSError) as erro:
        return (
            f"Não consegui gravar o resumo ({erro}). Nenhuma nota "
            "foi apagada."
        )

    # A partir daqui o resumo está em disco. Só agora os originais que
    # entraram nele podem ser removidos — um por um, e só esses.
    apagadas = 0

    for nota in arquivadas:
        try:
            notas.caminho_seguro(nota["caminho"]).unlink()
            apagadas += 1

        except (ValueError, OSError) as erro:
            print(
                f"[MEMORIA] Não consegui apagar o original "
                f"'{nota['titulo']}': {erro}"
            )

    print(
        f"[MEMORIA] Consolidação concluída: {apagadas} notas "
        f"resumidas em {caminho_resumo.name}."
    )

    return (
        f"Consolidei {apagadas} notas arquivadas em "
        f"{caminho_resumo.name}."
    )


# Uma passada completa: arquiva o que envelheceu e, se houver notas
# arquivadas suficientes, consolida.
def executar_varredura(forcar_consolidacao=False):
    if not config.configurado():
        return "A pasta do vault não está configurada."

    with _LOCK_VARREDURA:
        arquivadas = arquivar_notas_paradas()

        if arquivadas:
            print(
                f"[MEMORIA] {len(arquivadas)} nota(s) arquivada(s) "
                f"por falta de uso: {', '.join(arquivadas[:5])}"
            )

        resultado_consolidacao = consolidar_arquivo(
            forcar=forcar_consolidacao
        )

        controle = notas.ler_controle()
        controle["ultima_varredura"] = notas.agora()
        notas.escrever_controle(controle)

    return (
        f"{len(arquivadas)} nota(s) arquivada(s). "
        f"{resultado_consolidacao}"
    )


def precisa_varrer():
    if not config.configurado():
        return False

    controle = notas.ler_controle()
    dias = _quantos_dias_desde(controle.get("ultima_varredura"))

    if dias is None:
        return True

    return dias >= config.INTERVALO_VARREDURA_DIAS


# Roda a varredura numa thread de fundo, se já fizer tempo suficiente.
# Em background de propósito: ler dezenas de arquivos e, eventualmente,
# chamar o Gemini não pode atrasar a abertura do app.
def iniciar_varredura_periodica():
    global _thread_varredura

    if not config.configurado():
        return False

    if not precisa_varrer():
        return False

    if _thread_varredura is not None and _thread_varredura.is_alive():
        return False

    def trabalhar():
        try:
            print("[MEMORIA] Varredura periódica do vault iniciada.")
            print(f"[MEMORIA] {executar_varredura()}")

        except Exception as erro:
            print(f"[MEMORIA] Varredura falhou: {erro}")

    _thread_varredura = threading.Thread(
        target=trabalhar,
        name="memoria-varredura",
        daemon=True,
    )

    _thread_varredura.start()

    return True
