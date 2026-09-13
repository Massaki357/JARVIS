import base64

MIME_PADRAO = "image/jpeg"


def sistema(texto):
    from langchain.messages import SystemMessage

    return SystemMessage(texto)


def usuario(texto):
    from langchain.messages import HumanMessage

    return HumanMessage(texto)


def assistente(texto):
    from langchain.messages import AIMessage

    return AIMessage(texto)


def usuario_com_imagem(texto, imagem_bytes, mime=MIME_PADRAO):
    from langchain.messages import HumanMessage

    if not imagem_bytes:
        raise ValueError("Nenhuma imagem foi informada.")

    return HumanMessage(
        content=[
            {"type": "text", "text": texto},
            {
                "type": "image",
                "base64": base64.b64encode(imagem_bytes).decode("utf-8"),
                "mime_type": mime,
            },
        ]
    )


def do_historico(historico):
    convertidas = []

    for item in historico or []:
        if not isinstance(item, dict):
            continue

        conteudo = item.get("content")

        if not conteudo:
            continue

        papel = (item.get("role") or "").lower()

        if papel == "user":
            convertidas.append(usuario(conteudo))

        elif papel == "assistant":
            convertidas.append(assistente(conteudo))

        elif papel == "system":
            convertidas.append(sistema(conteudo))

    return convertidas


def montar(
    texto_usuario=None,
    instrucao_sistema=None,
    historico=None,
    imagem=None,
    mime_imagem=MIME_PADRAO,
):
    mensagens = []

    if instrucao_sistema:
        mensagens.append(sistema(instrucao_sistema))

    mensagens.extend(do_historico(historico))

    if imagem:
        mensagens.append(
            usuario_com_imagem(
                texto_usuario or "",
                imagem,
                mime_imagem,
            )
        )

    elif texto_usuario:
        mensagens.append(usuario(texto_usuario))

    if not mensagens:
        raise ValueError("Nenhuma mensagem foi montada para o agente.")

    return mensagens
