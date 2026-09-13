import win32com.client
import win32gui

from . import desktop


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


# Explorer primeiro, Área de Trabalho depois; None é diferente de (False, mensagem).
def obter_arquivo_selecionado():
    resultado = _obter_da_janela_explorer_ativa()

    if resultado is not None:
        return resultado

    return desktop.obter_item_selecionado_area_trabalho()
