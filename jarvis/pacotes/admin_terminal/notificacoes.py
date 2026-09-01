# Wrapper de notificação nativa do Windows (win11toast), com botões
# "Permitir"/"Negar". Cópia isolada e propositalmente independente do
# equivalente em jarvis/pacotes/rede_jarvis/notificacoes.py — admin_terminal não
# importa nada de rede_jarvis (ver CLAUDE.md/INTEGRATION.md: as duas
# funcionalidades ficam desconectadas nesta etapa por decisão
# explícita, não é acidente).
#
# IMPORTANTE: win11toast carrega bibliotecas nativas WinRT, que
# conflitam com a inicialização COM do Qt se forem carregadas ANTES
# do PySide6 no mesmo processo (derruba o processo com segmentation
# fault). Por isso o import fica dentro de cada função, não no topo
# do arquivo — mesma observação já documentada em
# jarvis/pacotes/rede_jarvis/notificacoes.py.
import threading


# Dispara uma notificação com botões "Permitir"/"Negar". ao_responder
# (concedido: bool) é chamado quando o usuário clicar em um dos
# botões. Se a notificação for apenas dispensada ou falhar,
# ao_responder não é chamado — quem chamou é responsável pelo próprio
# timeout (ver jarvis/pacotes/admin_terminal/confirmacao.py).
def notificar_pedido_confirmacao(titulo, mensagem, ao_responder):
    def _executar():
        try:
            from win11toast import toast

            resultado = toast(
                titulo,
                mensagem,
                buttons=[
                    {
                        "activationType": "protocol",
                        "arguments": "permitir",
                        "content": "Permitir",
                    },
                    {
                        "activationType": "protocol",
                        "arguments": "negar",
                        "content": "Negar",
                    },
                ],
            )

            argumentos = (
                resultado.get("arguments")
                if isinstance(resultado, dict)
                else None
            )

            if argumentos == "permitir":
                ao_responder(True)

            elif argumentos == "negar":
                ao_responder(False)

        except Exception as erro:
            print(
                "[admin_terminal] Falha ao exibir notificação de "
                f"confirmação: {erro}"
            )

    threading.Thread(
        target=_executar,
        daemon=True,
    ).start()
