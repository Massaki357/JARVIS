import threading


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
