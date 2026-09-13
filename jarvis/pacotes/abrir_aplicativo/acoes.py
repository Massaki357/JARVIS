import json

import os

import shutil

import subprocess

import unicodedata

import webbrowser

from pathlib import Path

from . import config


def normalizar_texto(texto):
    texto = str(texto).lower().strip()

    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )


def executar_comando(comando):
    subprocess.Popen(
        comando,

        shell=False
    )


def abrir_url(url):
    webbrowser.open(url)


def localizar_pasta_usuario(nomes):
    usuario = Path.home()

    onedrive = Path(
        os.getenv(
            "OneDrive",
            usuario / "OneDrive"
        )
    )

    bases = [
        usuario,
        onedrive,
    ]

    for base in bases:
        for nome in nomes:
            caminho = base / nome

            if caminho.exists() and caminho.is_dir():
                return caminho

    return None


def abrir_pasta_usuario(tipo):
    pastas = {
        "documentos": [
            "Documents",
            "Documentos",
        ],
        "downloads": [
            "Downloads",
        ],
        "videos": [
            "Videos",
            "Vídeos",
        ],
        "musicas": [
            "Music",
            "Músicas",
        ],
    }

    nomes = pastas.get(tipo)

    if not nomes:
        return False

    caminho = localizar_pasta_usuario(nomes)

    if not caminho:
        return False

    os.startfile(str(caminho))

    return True


def pastas_menu_iniciar():
    caminhos = []

    appdata = os.getenv("APPDATA")

    programdata = os.getenv("PROGRAMDATA")

    if appdata:
        caminhos.append(
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

    if programdata:
        caminhos.append(
            Path(programdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

    return [
        caminho
        for caminho in caminhos
        if caminho.exists()
    ]


def procurar_atalho_menu_iniciar(nome):
    procurado = normalizar_texto(nome)

    exatos = []

    parciais = []

    for pasta in pastas_menu_iniciar():
        for extensao in ("*.lnk", "*.url"):
            for atalho in pasta.rglob(extensao):
                nome_atalho = normalizar_texto(
                    atalho.stem
                )

                if nome_atalho == procurado:
                    exatos.append(atalho)

                elif procurado in nome_atalho:
                    parciais.append(atalho)

    candidatos = exatos or parciais

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda item: len(item.stem)
    )

    return candidatos[0]


def listar_aplicativos_windows():
    comando = (
        "Get-StartApps | "
        "Select-Object Name, AppID | "
        "ConvertTo-Json -Compress"
    )

    try:
        resultado = subprocess.run(
            [
                "powershell",

                "-NoProfile",

                "-Command",

                comando,
            ],

            capture_output=True,

            text=True,

            encoding="utf-8",

            errors="ignore",

            timeout=10,

            check=False,
        )

        if resultado.returncode != 0:
            return []

        texto = resultado.stdout.strip()

        if not texto:
            return []

        dados = json.loads(texto)

        if isinstance(dados, dict):
            dados = [dados]

        return dados

    except (
        subprocess.SubprocessError,
        json.JSONDecodeError,
        OSError,
    ):
        return []


def procurar_app_windows(nome):
    procurado = normalizar_texto(nome)

    exatos = []

    parciais = []

    for app in listar_aplicativos_windows():
        nome_app = app.get("Name", "")

        app_id = app.get("AppID", "")

        if not nome_app or not app_id:
            continue

        nome_normalizado = normalizar_texto(
            nome_app
        )

        if nome_normalizado == procurado:
            exatos.append(
                (nome_app, app_id)
            )

        elif procurado in nome_normalizado:
            parciais.append(
                (nome_app, app_id)
            )

    candidatos = exatos or parciais

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda item: len(item[0])
    )

    return candidatos[0]


def abrir_app_windows(nome):
    encontrado = procurar_app_windows(
        nome
    )

    if not encontrado:
        return None

    nome_app, app_id = encontrado

    executar_comando(
        [
            "explorer.exe",
            f"shell:AppsFolder\\{app_id}",
        ]
    )

    return nome_app


def abrir_executavel_conhecido(nome):
    executaveis = {
        "chrome": [
            "chrome.exe",
            "chrome",
        ],
        "google chrome": [
            "chrome.exe",
            "chrome",
        ],
        "edge": [
            "msedge.exe",
            "msedge",
        ],
        "microsoft edge": [
            "msedge.exe",
            "msedge",
        ],
        "word": [
            "winword.exe",
            "winword",
        ],
        "microsoft word": [
            "winword.exe",
            "winword",
        ],
        "excel": [
            "excel.exe",
            "excel",
        ],
        "microsoft excel": [
            "excel.exe",
            "excel",
        ],
        "steam": [
            "steam.exe",
            "steam",
        ],
    }

    procurado = normalizar_texto(nome)

    candidatos = executaveis.get(
        procurado,
        []
    )

    for executavel in candidatos:
        caminho = shutil.which(
            executavel
        )

        if caminho:
            executar_comando(
                [caminho]
            )

            return True

    return False


def abrir_especial(nome):
    nome = normalizar_texto(nome)

    aliases = {
        "meu computador": "meu_computador",
        "este computador": "meu_computador",
        "computador": "meu_computador",

        "explorador de arquivos": "explorador",
        "explorador": "explorador",

        "navegador": "navegador",
        "google": "navegador",

        "antivirus": "defender",
        "anti virus": "defender",
        "windows defender": "defender",
        "seguranca do windows": "defender",

        "configuracoes": "configuracoes",

        "calculadora": "calculadora",

        "relogio": "relogio",
        "alarme": "relogio",
        "relogio e alarmes": "relogio",

        "cmd": "cmd",
        "prompt de comando": "cmd",

        "powershell": "powershell",
        "power shell": "powershell",

        "bloco de notas": "notepad",
        "notepad": "notepad",

        "paint": "paint",

        "painel de controle": "painel",

        "meus documentos": "documentos",
        "documentos": "documentos",

        "meus downloads": "downloads",
        "downloads": "downloads",

        "meus videos": "videos",
        "videos": "videos",

        "minhas musicas": "musicas",
        "musicas": "musicas",
    }

    for apelido in sorted(
        aliases,
        key=len,
        reverse=True
    ):
        if apelido in nome:
            acao = aliases[apelido]

            if acao == "meu_computador":
                executar_comando(
                    [
                        "explorer.exe",
                        "shell:MyComputerFolder",
                    ]
                )
                return "Abrindo Meu Computador."

            if acao == "explorador":
                executar_comando(
                    ["explorer.exe"]
                )
                return "Abrindo o Explorador de Arquivos."

            if acao == "navegador":
                abrir_url(
                    "https://www.google.com"
                )
                return "Abrindo o navegador."

            if acao == "defender":
                os.startfile(
                    "windowsdefender:"
                )
                return "Abrindo a Segurança do Windows."

            if acao == "configuracoes":
                os.startfile(
                    "ms-settings:"
                )
                return "Abrindo as Configurações."

            if acao == "calculadora":
                executar_comando(
                    ["calc.exe"]
                )
                return "Abrindo a Calculadora."

            if acao == "relogio":
                os.startfile(
                    "ms-clock:"
                )
                return "Abrindo o Relógio."

            if acao == "cmd":
                executar_comando(
                    ["cmd.exe"]
                )
                return "Abrindo o Prompt de Comando."

            if acao == "powershell":
                executar_comando(
                    ["powershell.exe"]
                )
                return "Abrindo o PowerShell."

            if acao == "notepad":
                executar_comando(
                    ["notepad.exe"]
                )
                return "Abrindo o Bloco de Notas."

            if acao == "paint":
                executar_comando(
                    ["mspaint.exe"]
                )
                return "Abrindo o Paint."

            if acao == "painel":
                executar_comando(
                    ["control.exe"]
                )
                return "Abrindo o Painel de Controle."

            if acao in (
                "documentos",
                "downloads",
                "videos",
                "musicas",
            ):
                abriu = abrir_pasta_usuario(
                    acao
                )

                if abriu:
                    return (
                        f"Abrindo a pasta {acao}."
                    )

                return (
                    f"Não encontrei a pasta {acao} "
                    "neste computador."
                )

    return None


# Busca rasa (pasta + 1 nível), nunca rglob.
def abrir_de_pastas_extras(nome):
    procurado = normalizar_texto(nome)

    if not procurado:
        return None

    candidatos = []

    for pasta in config.pastas_extras():
        if not pasta.is_dir():
            continue

        try:
            candidatos.extend(
                list(pasta.glob("*.exe"))
                + list(pasta.glob("*/*.exe"))
            )

        except OSError:
            continue

    exatos = [
        executavel
        for executavel in candidatos
        if normalizar_texto(executavel.stem) == procurado
    ]

    parciais = [
        executavel
        for executavel in candidatos
        if procurado in normalizar_texto(executavel.stem)
    ]

    escolhido = None

    if exatos:
        escolhido = exatos[0]

    elif len(parciais) == 1:
        escolhido = parciais[0]

    if not escolhido:
        return None

    os.startfile(str(escolhido))

    return escolhido.stem


def abrir_aplicativo(nome):
    if not isinstance(nome, str):
        return "Nome do aplicativo inválido."

    nome = nome.strip()

    if not nome:
        return "Informe o nome do aplicativo que deseja abrir."

    try:
        resposta_especial = abrir_especial(
            nome
        )

        if resposta_especial:
            return resposta_especial

    except OSError as erro:
        return (
            "Não consegui abrir esse recurso do Windows. "
            f"Detalhes: {erro}"
        )

    try:
        atalho = procurar_atalho_menu_iniciar(
            nome
        )

        if atalho:
            os.startfile(str(atalho))

            return (
                f"Abrindo {atalho.stem}."
            )

    except OSError:
        pass

    try:
        nome_app = abrir_app_windows(
            nome
        )

        if nome_app:
            return (
                f"Abrindo {nome_app}."
            )

    except OSError:
        pass

    try:
        if abrir_executavel_conhecido(
            nome
        ):
            return (
                f"Abrindo {nome}."
            )

    except OSError:
        pass

    try:
        nome_extra = abrir_de_pastas_extras(
            nome
        )

        if nome_extra:
            return (
                f"Abrindo {nome_extra}."
            )

    except OSError:
        pass

    return (
        f"Não consegui localizar '{nome}' neste computador. "
        "Verifique se o aplicativo está instalado ou se aparece "
        "no Menu Iniciar do Windows."
    )
