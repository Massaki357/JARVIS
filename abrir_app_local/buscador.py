# Descobre e busca aplicativos instalados no Windows via
# Get-StartApps (PowerShell) — a mesma fonte de dados usada pela
# busca do menu Iniciar, cobrindo tanto apps tradicionais (.exe/
# atalhos do Programas) quanto apps da Microsoft Store (UWP). Nunca
# abre nada fora dessa lista — sem caminho arbitrário, sem comando
# livre vindo da fala do usuário.
import base64
import difflib
import json
import re
import subprocess
import unicodedata

# Tempo limite, em segundos, para o Get-StartApps responder.
TIMEOUT_SEGUNDOS = 20

# Get-StartApps monta o comando dentro do PowerShell e devolve o
# resultado como base64 de bytes UTF-8 (em vez de deixar o texto
# passar cru pelo pipe capturado do subprocess) — testado e
# confirmado que é necessário: sem isso, nomes com acento vêm
# corrompidos (ex: "Câmera" virava "C?mera") mesmo forçando UTF-8 em
# toda a cadeia de captura do lado do Python. Base64 é puro ASCII,
# então não sofre nenhuma conversão de codepage no caminho de volta.
#
# LIMITAÇÃO CONHECIDA (não é bug desta ponte, confirmado testando 4
# abordagens diferentes — inclusive escrevendo direto num arquivo
# UTF-8, sem pipe nenhum no meio): alguns apps embutidos do Windows
# (ex: "Câmera", "Configurações", "Calendário") têm o nome resolvido
# via referência de recurso indireta (@{Pacote!ms-resource:...}), e
# essa resolução já vem corrompida do próprio Get-StartApps quando
# chamado de fora de uma sessão interativa — antes mesmo de qualquer
# conversão de bytes acontecer aqui. Afeta só esse punhado de apps de
# sistema com nome acentuado; apps de terceiros (Spotify, Chrome,
# Steam, etc.) não são afetados.
_COMANDO_PS = (
    "$json = Get-StartApps | ConvertTo-Json -Compress; "
    "if (-not $json) { $json = '[]' } "
    "$bytes = [System.Text.Encoding]::UTF8.GetBytes($json); "
    "[Convert]::ToBase64String($bytes)"
)


# Padroniza um texto para comparação aproximada (minúsculas, sem
# acento, sem espaço duplicado) — mesmo approach já usado em
# memory_manager.py e casa_inteligente/dispositivos_tuya.py. Copiado
# aqui em vez de importado de outro pacote, de propósito: este é um
# pacote isolado, independente do resto do projeto.
def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    # Hífen vira espaço antes de colapsar espaços — quem fala não
    # pronuncia hífen ("7-Zip" precisa bater com "7 zip" dito por
    # voz).
    texto = texto.replace("-", " ")

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


# Lista todos os apps que aparecem na busca do menu Iniciar do
# Windows (Get-StartApps), cada um como {"nome", "app_id"}. Nunca
# lança exceção — retorna lista vazia se o PowerShell falhar ou a
# saída vier em formato inesperado, por qualquer motivo.
def listar_apps_instalados():
    try:
        resultado = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                _COMANDO_PS,
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEGUNDOS,
        )

    except (subprocess.SubprocessError, OSError) as erro:
        print(
            f"[abrir_app_local] Falha ao listar apps instalados: {erro}"
        )
        return []

    if resultado.returncode != 0 or not resultado.stdout.strip():
        print(
            "[abrir_app_local] Get-StartApps não retornou dados "
            f"(código {resultado.returncode}): "
            f"{resultado.stderr.strip()[:200]}"
        )
        return []

    try:
        json_bytes = base64.b64decode(
            resultado.stdout.strip()
        )
        dados = json.loads(
            json_bytes.decode("utf-8")
        )

    except (ValueError, UnicodeDecodeError) as erro:
        print(
            f"[abrir_app_local] Saída inesperada do Get-StartApps: {erro}"
        )
        return []

    # ConvertTo-Json devolve um objeto único (não uma lista) quando
    # só existe um resultado — normaliza pra sempre trabalhar com
    # uma lista.
    if isinstance(dados, dict):
        dados = [dados]

    if not isinstance(dados, list):
        return []

    apps = []

    for item in dados:
        if not isinstance(item, dict):
            continue

        nome = item.get("Name")
        app_id = item.get("AppID")

        if nome and app_id:
            apps.append(
                {
                    "nome": nome,
                    "app_id": app_id,
                }
            )

    return apps


# Encontra o(s) app(s) cujo nome mais se aproxima de nome_falado.
# Retorna (candidato, None) se achar exatamente um; (None,
# candidatos) se achar mais de um (lista de dicts, pra desambiguar);
# (None, []) se não achar nenhum. Nunca escolhe sozinho quando há
# ambiguidade.
def buscar_app(nome_falado):
    apps = listar_apps_instalados()

    if not apps:
        return None, []

    alvo = _normalizar(nome_falado)

    # Primeira tentativa: correspondência exata.
    exatos = [
        app
        for app in apps
        if _normalizar(app["nome"]) == alvo
    ]

    if len(exatos) == 1:
        return exatos[0], None

    if len(exatos) > 1:
        return None, exatos

    # Segunda tentativa: correspondência parcial (substring, em
    # qualquer direção).
    parciais = [
        app
        for app in apps
        if alvo in _normalizar(app["nome"])
        or _normalizar(app["nome"]) in alvo
    ]

    if len(parciais) == 1:
        return parciais[0], None

    if len(parciais) > 1:
        return None, parciais

    # Terceira tentativa: correspondência aproximada, tolerando
    # pequenas imprecisões do reconhecimento de voz (ex: "espotify"
    # ainda encontrar "Spotify").
    apps_por_nome_normalizado = {
        _normalizar(app["nome"]): app
        for app in apps
    }

    proximos = difflib.get_close_matches(
        alvo,
        apps_por_nome_normalizado.keys(),
        n=5,
        cutoff=0.72,
    )

    candidatos_aproximados = [
        apps_por_nome_normalizado[nome]
        for nome in proximos
    ]

    if len(candidatos_aproximados) == 1:
        return candidatos_aproximados[0], None

    if len(candidatos_aproximados) > 1:
        return None, candidatos_aproximados

    return None, []
