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
import re
import threading
import time
from datetime import datetime, timedelta

# Instrução de resumo enviada ao Gemini na consolidação — centralizada
# em jarvis/nucleo/prompts/, seção MEMORIA_OBSIDIAN.
from jarvis.nucleo import prompts

from . import config, escritor, notas

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


# Uma chamada de texto simples ao Gemini (sem voz, sem sessão Live),
# com retentativa em espera crescente — extraído de _gerar_resumo pra
# ser reaproveitado por salvar_resumo_conversa, mais abaixo, sem
# duplicar a lógica de retentativa. Devolve (sucesso, texto).
#
# Erros temporários (503 de modelo sobrecarregado, 429 de limite)
# aconteceram de verdade no primeiro teste real desta função, e sem
# retentativa eles significavam simplesmente pular a operação. Como
# isto sempre roda numa thread de fundo, sem ninguém esperando ao
# vivo, esperar alguns segundos não custa nada.
def _chamar_modelo_texto(pedido):
    chave = (os.getenv("GEMINI_API_KEY") or "").strip()

    if not chave:
        return False, "GEMINI_API_KEY não configurada."

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

            ultimo_erro = "O modelo devolveu uma resposta vazia."

        except Exception as erro:
            ultimo_erro = f"Falha ao chamar o modelo: {erro}"

            print(
                f"[MEMORIA] Tentativa {tentativa + 1} de "
                f"{config.TENTATIVAS_CONSOLIDACAO} falhou: "
                f"{str(erro)[:120]}"
            )

    return False, ultimo_erro


# Pede ao Gemini um resumo condensado das notas arquivadas. Devolve
# (sucesso, texto).
def _gerar_resumo(notas_arquivadas):
    blocos = []

    for nota in notas_arquivadas:
        blocos.append(f"### {nota['titulo']}\n{nota['corpo']}")

    pedido = prompts.CONSOLIDACAO_RESUMO_ARQUIVO.format(
        blocos="\n\n".join(blocos)
    )

    return _chamar_modelo_texto(pedido)


# Mínimo de turnos (user+assistant, um cada) na transcrição pra valer
# a pena gerar e salvar um resumo de conversa — evita poluir o vault
# com chamadas triviais/vazias.
MINIMO_MENSAGENS_RESUMO_CONVERSA = 4


# Gera um título + resumo de uma conversa (lista de {"role", "content"}
# — mesmo formato de jarvis.gemini.cliente_live.py:self.transcricao_conversa)
# e salva como uma memória pesquisável, chamada no fim de uma chamada
# do Gemini — pra "como estava aquela conversa sobre X" numa chamada
# futura encontrar alguma coisa via buscar_memorias_relacionadas.
# Reaproveita escritor.salvar_memoria (mesma deduplicação, link
# automático e escrita atômica de qualquer outra memória — nada novo
# precisou ser inventado aqui pra gravar). Nunca levanta exceção.
# Devolve (sucesso, mensagem).
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

    # Separa TÍTULO/RESUMO da resposta — formato fixo pedido no
    # prompt, mas nunca confia cegamente nele: cai num título
    # genérico com data se o modelo fugir do formato, em vez de
    # descartar o resumo inteiro por causa disso.
    titulo = None
    linhas_resumo = []
    capturando_resumo = False

    for linha in resposta.splitlines():
        # T[IÍ]TULO em vez de "TÍTULO" literal: o modelo às vezes
        # devolve sem o acento mesmo quando o prompt pede com acento
        # — visto ao vivo escrevendo este teste. re.match ancora no
        # início da linha (equivalente ao startswith de antes).
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
