"""
Construção das mensagens enviadas a um agente, no formato único do
LangChain — SystemMessage / HumanMessage / AIMessage.

É AQUI que "padronizar os dados enviados" acontece de fato. Antes,
o mesmo conceito tinha um formato diferente por provedor:

  - Groq/Cerebras/OpenAI: [{"role": "user", "content": "..."}]
  - Gemini: contents=[types.Part.from_bytes(...), "pergunta"],
            com system_instruction num parâmetro separado
  - Mistral: content como lista, com a imagem em
            {"type": "image_url", "image_url": "data:image/jpeg;base64,..."}
            — string PLANA, não o objeto {"url": ...} que a OpenAI usa

Aquela última diferença é o exemplo perfeito do problema: errar a
forma não falhava de modo óbvio, e por isso ela está anotada em dois
arquivos deste projeto para não ser esquecida. Agora a forma é uma
só, e quem traduz para cada provedor é o LangChain.

O BLOCO DE IMAGEM usa o formato padrão de conteúdo do LangChain —
{"type": "image", "base64": ..., "mime_type": ...} —, que funciona
igual no Gemini e na Mistral. Não é o formato antigo "image_url" de
nenhum dos dois.
"""

import base64

# MIME das imagens que este projeto produz. Toda captura (tela,
# câmera, visualização remota) sai em JPEG — ver jarvis/servicos/
# visao/. Fica como padrão para ninguém precisar repetir.
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
    """
    Uma mensagem de usuário com texto + imagem, a partir dos BYTES da
    imagem já em memória.

    Nenhuma captura deste projeto é gravada em disco antes de ser
    enviada, e isso continua verdade aqui: o base64 é feito em
    memória e nada toca o sistema de arquivos.
    """
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
    """
    Converte o histórico no formato de dicionário que este projeto já
    usa em vários lugares — [{"role": "user"|"assistant", "content":
    str}] — para mensagens do LangChain.

    Esse formato é o mesmo de self.transcricao_conversa do cérebro do
    Gemini e o mesmo que processar_turno() já recebia, então nenhum
    chamador precisou mudar o jeito de guardar conversa por causa
    desta camada.

    Papéis desconhecidos são ignorados em silêncio, em vez de
    derrubarem o turno: um item estranho no histórico nunca pode
    custar a mensagem que o usuário acabou de falar.
    """
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
    """
    A lista completa de mensagens de um turno, na ordem que todo
    provedor espera: instrução de sistema, histórico, e por último a
    mensagem do usuário (com a imagem junto, quando houver).

    Devolve uma lista pronta para modelo.invoke(). Levanta ValueError
    se não sobrar mensagem nenhuma — mandar uma conversa vazia para o
    modelo só renderia um erro pior lá na frente.
    """
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
