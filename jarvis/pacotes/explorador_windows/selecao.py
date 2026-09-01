# Descobre o(s) arquivo(s) selecionado(s) na janela do Windows
# Explorer que está em primeiro plano — usado pelo fluxo "envie este
# arquivo que eu selecionei" de enviar_email (ver
# jarvis/gemini/cliente_live.py). Depende de pywin32 (win32com/
# win32gui), só funciona no Windows.
import win32com.client
import win32gui


# Retorna (sucesso: bool, resultado):
#   sucesso=True  -> resultado é uma lista de caminhos absolutos
#                     (str) dos itens selecionados na janela do
#                     Explorer em primeiro plano. Pode ter mais de
#                     um item — quem chama decide o que fazer nesse
#                     caso (nunca escolhe silenciosamente só o
#                     primeiro).
#   sucesso=False -> resultado é uma mensagem em português explicando
#                     por que nada foi encontrado (nenhuma janela do
#                     Explorer em primeiro plano, ou nenhum item
#                     selecionado nela) — nunca adivinha ou escolhe
#                     um arquivo por conta própria nesses casos.
def obter_arquivo_selecionado():
    handle_ativo = win32gui.GetForegroundWindow()

    if not handle_ativo:
        return False, "Não foi possível identificar a janela em primeiro plano."

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

    return False, (
        "Nenhuma janela do Explorer de arquivos está em primeiro "
        "plano agora."
    )
