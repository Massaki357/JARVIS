# Abre um app já resolvido (por buscador.py ou pelo cache) — nunca
# um caminho/comando arbitrário vindo direto da fala do usuário, só
# o AppID que o próprio Windows já listou via Get-StartApps.
import os
import re
import subprocess

# AppIDs que já são um caminho de arquivo de verdade (letra de
# unidade + ":\") podem ser abertos direto via os.startfile — mesmo
# mecanismo do "abrir arquivo" padrão do Windows (equivalente a dar
# duplo clique nele).
_PADRAO_CAMINHO_ABSOLUTO = re.compile(r"^[A-Za-z]:\\")

# AppIDs no formato de URI de protocolo (ex: "steam://rungameid/...")
# também abrem direto via os.startfile — ele já sabe resolver
# protocolos registrados no Windows, mesma base do ShellExecute.
_PADRAO_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


# Abre o app descrito por app_info ({"nome", "app_id"}, vindo de
# buscador.buscar_app ou do cache). Nunca lança exceção — sempre
# retorna (sucesso: bool, mensagem: str).
#
# A maioria dos AppIDs do Get-StartApps NÃO é um caminho de arquivo
# utilizável direto, mesmo pra apps tradicionais (não-UWP) —
# confirmado testando ao vivo antes de escrever esta função: um app
# comum como o 7-Zip tem AppID "{GUID}\7-Zip\7zFM.exe", que parece
# um caminho mas é na verdade um identificador de namespace do Shell
# (o GUID é a pasta especial "Programs" do menu Iniciar) — não algo
# que os.startfile consiga abrir sozinho (não existe um diretório
# real com esse nome). O único jeito confiável de abrir QUALQUER
# AppID nesse formato — com "!" (UWP), sem "!" (pacote UWP sem app
# explícito) ou com GUID (atalho tradicional do Menu Iniciar) — é
# através da pasta virtual AppsFolder do Explorer, testada e
# confirmada abrindo o 7-Zip de verdade. Só quando o AppID já é um
# caminho absoluto de verdade ou uma URI de protocolo é que
# os.startfile é usado direto, também confirmado contra apps reais
# instalados nesta máquina.
def abrir(app_info):
    app_id = (app_info or {}).get("app_id", "")
    nome = (app_info or {}).get("nome", "aplicativo")

    if not app_id:
        return False, f"'{nome}' não tem um identificador válido pra abrir."

    try:
        if (
            _PADRAO_CAMINHO_ABSOLUTO.match(app_id)
            or _PADRAO_URI.match(app_id)
        ):
            os.startfile(app_id)

        else:
            subprocess.run(
                [
                    "explorer.exe",
                    f"shell:AppsFolder\\{app_id}",
                ],
                check=False,
            )

    except OSError as erro:
        return False, f"Falha ao abrir '{nome}': {erro}"

    return True, f"'{nome}' aberto."
