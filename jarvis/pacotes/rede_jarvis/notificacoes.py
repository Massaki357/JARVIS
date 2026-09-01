# win11toast exibe notificações nativas do Windows (toast), incluindo
# botões de ação. toast() é bloqueante (espera clique/dispensa/falha),
# por isso sempre é chamada dentro de uma thread própria aqui.
#
# IMPORTANTE: win11toast carrega bibliotecas nativas WinRT, que
# conflitam com a inicialização COM do Qt se forem carregadas ANTES
# do PySide6 no mesmo processo (derruba o processo com segmentation
# fault). Por isso o import fica dentro de cada função, não no topo
# do arquivo — assim só é carregado depois do app (e do PySide6) já
# estarem de pé.
import threading


# Dispara uma notificação simples, sem esperar por interação (usada
# para avisos informativos, como "recebendo arquivo de X").
def notificar_simples(titulo, mensagem):
    def _executar():
        try:
            from win11toast import toast

            toast(
                titulo,
                mensagem,
            )

        except Exception as erro:
            print(
                f"[rede_jarvis] Falha ao exibir notificação: {erro}"
            )

    threading.Thread(
        target=_executar,
        daemon=True,
    ).start()


# Dispara uma notificação com botões "Permitir"/"Negar". ao_responder
# (concedido: bool) é chamado quando o usuário clicar em um dos
# botões. Se a notificação for apenas dispensada ou falhar,
# ao_responder não é chamado — quem chamou é responsável pelo próprio
# timeout (ver jarvis/pacotes/rede_jarvis/permissoes.py).
def notificar_pedido_permissao(titulo, mensagem, ao_responder):
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
                "[rede_jarvis] Falha ao exibir notificação de "
                f"permissão: {erro}"
            )

    threading.Thread(
        target=_executar,
        daemon=True,
    ).start()
