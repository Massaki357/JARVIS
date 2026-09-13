import threading


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
