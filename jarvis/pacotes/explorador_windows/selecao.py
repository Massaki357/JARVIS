# Descobre o(s) arquivo(s) selecionado(s) — primeiro numa janela do
# Windows Explorer em primeiro plano; se não houver nenhuma (ex: o
# usuário está com o foco na própria Área de Trabalho, que não
# aparece como uma janela do Explorer pra Shell.Application), cai
# pro fallback de checar se há algo selecionado na Área de Trabalho
# em si (ver desktop.py). Usado pelo fluxo "envie este arquivo que
# eu selecionei" de preparar_email (ver
# jarvis/gemini/cliente_live.py). Depende de pywin32 (win32com/
# win32gui), só funciona no Windows.
import win32com.client
import win32gui

from . import desktop


# Tenta achar o item selecionado numa janela do Explorer em primeiro
# plano. Retorna (True, [caminhos]) | (False, mensagem) — igual
# obter_arquivo_selecionado() — ou None quando nenhuma janela do
# Explorer corresponde à janela em primeiro plano (sentinela
# deliberadamente distinta de (False, mensagem): None significa
# "não é o caso desta função, tente outra coisa"; (False, mensagem)
# significa "era uma janela do Explorer, mas não tinha nada
# selecionado nela" — esse segundo caso NÃO cai pro fallback da Área
# de Trabalho, porque o usuário claramente tinha uma janela do
# Explorer em foco e a resposta certa é avisar que ela está vazia,
# não ir procurar seleção em outro lugar).
def _obter_da_janela_explorer_ativa():
    handle_ativo = win32gui.GetForegroundWindow()

    if not handle_ativo:
        return None

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        janelas = shell.Windows()

    except Exception as erro:
        return False, f"Falha ao acessar as janelas do Explorer: {erro}"

    for janela in janelas:
        try:
            if janela.HWND != handle_ativo:
                continue

            itens_selecionados = janela.Document.SelectedItems()

        except Exception:
            # Não é uma janela de arquivos (ex: uma aba do Internet
            # Explorer, Painel de Controle) ou não expõe
            # Document/SelectedItems — ignora e continua procurando
            # entre as demais janelas abertas do Shell.
            continue

        if itens_selecionados.Count == 0:
            return False, (
                "A janela do Explorer em primeiro plano não tem "
                "nenhum arquivo selecionado."
            )

        caminhos = [
            itens_selecionados.Item(indice).Path
            for indice in range(itens_selecionados.Count)
        ]

        return True, caminhos

    return None


# Retorna (sucesso: bool, resultado):
#   sucesso=True  -> resultado é uma lista de caminhos absolutos
#                     (str) dos itens selecionados — numa janela do
#                     Explorer em primeiro plano, ou, na falta dela,
#                     na Área de Trabalho. Pode ter mais de um item —
#                     quem chama decide o que fazer nesse caso (nunca
#                     escolhe silenciosamente só o primeiro).
#   sucesso=False -> resultado é uma mensagem em português explicando
#                     por que nada foi encontrado — nunca adivinha ou
#                     escolhe um arquivo por conta própria nesses
#                     casos.
def obter_arquivo_selecionado():
    resultado = _obter_da_janela_explorer_ativa()

    if resultado is not None:
        return resultado

    return desktop.obter_item_selecionado_area_trabalho()
