import os
import re
import threading
from datetime import datetime, timedelta

from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config, escritor, notas

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


def deve_podar(nota, agora=None):
    frontmatter = nota["frontmatter"]

    # pinned isenta sempre; os 3 critérios de poda valem juntos (docs/memoria_obsidian.md).
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


def _nome_resumo(momento=None):
    momento = momento or datetime.now()
    trimestre = (momento.month - 1) // 3 + 1

    return f"resumo-{momento.year}-Q{trimestre}.md"


TIMEOUT_CONSOLIDACAO_SEGUNDOS = 60


def _chamar_modelo_texto(pedido):
    chave = (os.getenv("GEMINI_API_KEY") or "").strip()

    if not chave:
        return False, "GEMINI_API_KEY não configurada."

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="gemini",
            modelo=config.MODELO_CONSOLIDACAO,
            api_key=chave,
            texto=pedido,
            timeout=TIMEOUT_CONSOLIDACAO_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(
            tentativas=config.TENTATIVAS_CONSOLIDACAO,
            espera_base=config.ESPERA_ENTRE_TENTATIVAS_SEGUNDOS,
            espera_maxima=(
                config.ESPERA_ENTRE_TENTATIVAS_SEGUNDOS
                * config.TENTATIVAS_CONSOLIDACAO
            ),
            rotulo="MEMORIA",
        ),
    )

    if not resposta.sucesso:
        return False, f"Falha ao chamar o modelo: {resposta.erro}"

    if not resposta.texto:
        return False, "O modelo devolveu uma resposta vazia."

    return True, resposta.texto


def _gerar_resumo(notas_arquivadas):
    blocos = []

    for nota in notas_arquivadas:
        blocos.append(f"### {nota['titulo']}\n{nota['corpo']}")

    pedido = prompts.CONSOLIDACAO_RESUMO_ARQUIVO.format(
        blocos="\n\n".join(blocos)
    )

    return _chamar_modelo_texto(pedido)


MINIMO_MENSAGENS_RESUMO_CONVERSA = 4


def salvar_resumo_conversa(transcricao):
    if not config.configurado():
        return False, "A pasta do vault não está configurada."

    transcricao = list(transcricao or [])

    if len(transcricao) < MINIMO_MENSAGENS_RESUMO_CONVERSA:
        return False, "Conversa curta demais pra valer a pena resumir."

    texto_transcricao = "\n".join(
        f"{'Usuário' if turno.get('role') == 'user' else 'Assistente'}: "
        f"{turno.get('content', '')}"
        for turno in transcricao
    )

    pedido = prompts.CONSOLIDACAO_RESUMO_CONVERSA.format(
        transcricao=texto_transcricao
    )

    sucesso, resposta = _chamar_modelo_texto(pedido)

    if not sucesso:
        print(f"[MEMORIA] Não consegui resumir a conversa: {resposta}")
        return False, resposta

    titulo = None
    linhas_resumo = []
    capturando_resumo = False

    for linha in resposta.splitlines():
        if re.match(r"T[IÍ]TULO\s*:", linha.strip(), re.IGNORECASE):
            titulo = linha.split(":", 1)[1].strip()

        elif re.match(r"RESUMO\s*:", linha.strip(), re.IGNORECASE):
            capturando_resumo = True
            resto = linha.split(":", 1)[1].strip()

            if resto:
                linhas_resumo.append(resto)

        elif capturando_resumo:
            linhas_resumo.append(linha)

    resumo = "\n".join(linhas_resumo).strip() or resposta.strip()

    if not titulo:
        titulo = f"Conversa de {notas.agora()[:16].replace('T', ' ')}"

    resultado = escritor.salvar_memoria(titulo, resumo)

    print(f"[MEMORIA] {resultado}")

    return True, resultado


# Ordem obrigatória: resumo gravado em disco ANTES de apagar as notas originais.
def consolidar_arquivo(forcar=False):
    if not config.configurado():
        return "A pasta do vault não está configurada."

    notas.garantir_pastas()

    arquivadas = [
        nota for nota in notas.listar_notas(incluir_arquivo=True)
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
