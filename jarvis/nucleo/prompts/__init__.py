# Todo texto de instrução hardcoded enviado a algum modelo (Gemini,
# Groq, Cerebras, OpenAI, Mistral) neste projeto vive aqui —
# centralizado numa tarefa dedicada, para reaproveitamento e
# organização, sem alterar nenhum texto final que chega a cada
# modelo (cada extração foi verificada byte a byte contra o texto
# original antes de qualquer coisa ser movida).
#
# Prompts curtos (uma a poucas frases) são constante Python aqui
# embaixo, organizados em seções por pacote/arquivo de origem —
# padrão usado no resto do projeto pra texto de instrução curto
# (ver MENSAGEM_INDISPONIVEL em delegacao_ia, por exemplo, que já
# seguia essa convenção antes desta tarefa).
#
# Os dois prompts realmente grandes e multi-seção (a instrução de
# sistema completa da sessão Gemini Live e o bloco de autenticação)
# NÃO viraram string Python: são arquivos .md ao lado deste, porque
# uma constante de ~22 mil caracteres numa linha só seria ilegível e
# impossível de revisar num diff. Ver a seção "GEMINI LIVE —
# instrução de sistema" no fim deste arquivo para como eles são
# carregados.
#
# Nome do pacote: por que "jarvis/nucleo/prompts/" e não
# "jarvis/nucleo/prompts.py" — Python não permite um módulo e um
# pacote (pasta com __init__.py) de mesmo nome lado a lado na mesma
# pasta, e os arquivos .md precisavam morar dentro de "prompts/".
# Resolvido transformando prompts num pacote: este __init__.py é
# importado exatamente como um módulo prompts.py seria
# (`from jarvis.nucleo import prompts`, `prompts.ANUNCIO_ESPONTANEO`
# funcionam igual), só que agora os .md moram dentro da mesma pasta,
# não ao lado dela.
from pathlib import Path

_PASTA = Path(__file__).resolve().parent


# ============================================================
# GEMINI LIVE — jarvis/gemini/cliente_live.py
# Prompts pontuais enviados via send_client_content durante a sessão
# (a instrução de sistema completa fica no fim deste arquivo).
# ============================================================

# Anúncio espontâneo: o worker "fala" algo sem o usuário ter
# perguntado nada agora (aviso de permissão remota, resultado de um
# comando administrativo confirmado fora da conversa, fim do timeout
# de inatividade, etc.) — usado por _enviar_anuncio_espontaneo, e
# reaproveitado por rede_jarvis/admin_terminal via callback_falar.
ANUNCIO_ESPONTANEO = (
    "[SISTEMA] Diga isso em voz alta agora, com suas próprias "
    "palavras, de forma natural e breve: {texto}"
)

# Cruzamento de segunda opinião visual: reenvia a MESMA imagem já
# usada numa consulta externa (Pl@ntNet ou Mistral) pedindo pro
# Gemini olhar com a própria visão e comparar, em vez de só repassar
# o resultado externo sem checagem — usado por
# enviar_imagem_para_cruzamento (identificar_planta e
# consultar_segunda_opiniao_visual).
CRUZAMENTO_SEGUNDA_OPINIAO = (
    "[SISTEMA] Esta é exatamente a mesma imagem usada na consulta "
    "de {contexto}. Resultado obtido dessa fonte externa: "
    "{resultado_externo} Observe a imagem você mesmo agora, com sua "
    "própria visão, e compare com esse resultado — diga "
    "explicitamente se concorda ou diverge ao responder. Não "
    "repasse o resultado externo como se fosse a única opinião, e "
    "não afirme nada que você não consiga confirmar olhando a "
    "imagem você mesmo."
)

# Análise pontual de uma captura de tela ou câmera — UNIFICADO: antes
# existiam duas cópias quase idênticas em enviar_tela_para_gemini e
# enviar_camera_para_gemini, diferindo só na palavra "tela"/"câmera".
# {origem} recebe uma das duas (ambas usam o artigo "da", por isso
# nenhum outro ajuste de gênero é necessário).
ANALISE_IMAGEM_PONTUAL = (
    "Analise exatamente esta imagem da {origem} enviada neste "
    "turno. Ignore imagens anteriores. Use somente esta imagem "
    "como base. Não chame nenhuma função visual. Não chute. Se a "
    "imagem não estiver clara, diga que não conseguiu ver bem. "
    "Explique de forma objetiva o que está vendo."
)


# ============================================================
# ENVIO DE ARQUIVO PELA UI — jarvis/ui/janela_envio_arquivo.py
# Ambos entram na sessão Live via GeminiLiveWorker.enviar_texto_da_ui
# / enviar_imagem_da_ui (send_realtime_input) — ver o comentário
# sobre chat_jarvis no CLAUDE.md pra por que esse caminho usa um
# mecanismo diferente do resto (send_realtime_input, não
# send_client_content).
# ============================================================

CONTEXTO_IMAGEM_ENVIADA = (
    "[SISTEMA] O usuário acabou de enviar a imagem '{nome}' como "
    "contexto adicional — considere essa imagem na conversa."
)

CONTEXTO_ARQUIVO_ENVIADO = (
    "[SISTEMA] O usuário enviou o seguinte arquivo como contexto "
    "({nome_arquivo}){aviso_truncamento}:\n\n{texto_truncado}"
)


# ============================================================
# DELEGACAO_IA — jarvis/pacotes/delegacao_ia/roteador.py
# (Groq/Cerebras/OpenAI, por trás de delegar_tarefa) — textos
# devolvidos como resultado da tool ao Gemini, não prompts para os
# provedores em si (provedores.py manda o "conteudo" cru, sem
# nenhuma instrução hardcoded própria — ver a nota em
# _chamar_completions).
# ============================================================

DELEGACAO_INDISPONIVEL = (
    "Delegação indisponível no momento (todos os provedores "
    "falharam). Responda a solicitação você mesmo, com seu próprio "
    "raciocínio, sem mencionar essa falha ao usuário."
)

DELEGACAO_SEGUNDA_OPINIAO_INDISPONIVEL = (
    "Não foi possível consultar uma segunda opinião agora (falha ao "
    "acessar a OpenAI). Responda a solicitação você mesmo, com seu "
    "próprio raciocínio, e avise ao usuário que não conseguiu "
    "confirmar essa resposta com uma segunda IA neste momento."
)

DELEGACAO_SEGUNDA_OPINIAO_RESULTADO = (
    "[SEGUNDA OPINIÃO — OPENAI]\n"
    "{resultado}\n\n"
    "Compare essa resposta com o seu próprio raciocínio sobre o "
    "mesmo assunto e responda ao usuário sintetizando os dois "
    "pontos de vista: onde concordam, onde divergem, e qual "
    "conclusão parece mais sólida. Não repasse a resposta acima "
    "como se fosse a única opinião."
)


# ============================================================
# IDENTIFICACAO_VISUAL — jarvis/pacotes/identificacao_visual/
# mistral_vision_client.py (Mistral, com entrada de imagem)
# ============================================================

# Pergunta padrão quando o usuário não deu uma pergunta específica —
# essa sim é enviada de verdade pra Mistral, junto com a imagem (as
# outras duas constantes desta seção voltam pro Gemini como tool
# result).
VISAO_PERGUNTA_PADRAO = "O que é isso na imagem?"

# Texto devolvido ao Gemini quando a consulta à Mistral falha por
# qualquer motivo — instrui a responder só com a própria visão.
VISAO_INDISPONIVEL = (
    "Não foi possível obter uma segunda opinião da Mistral "
    "({motivo}). Responda usando só sua própria visão e avise "
    "o usuário que não conseguiu confirmar com uma segunda "
    "fonte desta vez."
)


# ============================================================
# MEMORIA_OBSIDIAN — jarvis/pacotes/memoria_obsidian/consolidacao.py
# (Gemini, chamada de texto simples — a consolidação em background
# das notas arquivadas, sem voz nem UI).
# ============================================================

CONSOLIDACAO_RESUMO_ARQUIVO = (
    "Abaixo estão anotações antigas de um assistente pessoal, "
    "que ficaram muito tempo sem uso e vão ser descartadas.\n\n"
    "Escreva um resumo condensado, em português do Brasil, "
    "preservando SOMENTE o que ainda pode ser útil no futuro: "
    "fatos sobre a pessoa, preferências, nomes, contatos, "
    "decisões. Descarte o que for irrelevante, repetido ou "
    "efêmero.\n\n"
    "Organize em tópicos curtos, um por linha, começando com "
    "'- '. Não invente nada que não esteja nas anotações. Se "
    "nada valer a pena preservar, responda apenas: (nada a "
    "preservar)\n\n"
    "{blocos}"
)


# ============================================================
# CEREBRO_RESERVA — jarvis/pacotes/cerebro_reserva/cerebro.py
# (Mistral, chat com ferramentas — assume a conversa por voz quando
# a sessão do Gemini Live falha).
# ============================================================

# Deliberadamente NÃO repete a identidade e as regras completas da
# instrução de sistema principal (~22 mil caracteres): cada turno já
# carrega ~5k tokens de schema de ferramentas, e mandar o prompt
# inteiro junto estouraria a cota de tokens por minuto sem melhorar
# a resposta. O essencial da conduta de cada ferramenta já viaja
# dentro da própria descrição dela.
CEREBRO_RESERVA_INSTRUCAO_SISTEMA = (
    "Você é o ALFRED, um assistente pessoal por voz. "
    "Fale sempre em português do Brasil. "
    "Suas respostas são faladas em voz alta, então escreva como se "
    "falasse: frases curtas, no máximo três, sem listas, sem "
    "markdown, sem emojis e sem títulos. "
    "Seja inteligente, natural, prestativo e elegante, com humor "
    "sutil e ocasional. Não concorde automaticamente com tudo: se "
    "uma ideia for ruim ou arriscada, diga isso com elegância. "
    "Use as funções disponíveis apenas quando o usuário pedir "
    "claramente a ação correspondente — nunca por iniciativa "
    "própria e nunca só para confirmar algo que você já sabe. "
    "Se uma função devolver mais de uma opção possível, pergunte ao "
    "usuário qual delas antes de agir, nunca escolha sozinho. "
    "Nunca invente que executou algo que não executou. "
    "Quando o usuário pedir para encerrar, desligar, parar ou "
    "terminar a chamada, você PRECISA chamar a função "
    "encerrar_chamada. Só se despedir sem chamá-la não encerra nada "
    "e deixa o usuário falando sozinho. "
    "Nunca mencione qual tecnologia, modelo ou serviço está te "
    "respondendo, e nunca comente que houve qualquer falha, troca "
    "de sistema ou modo alternativo: apenas continue a conversa "
    "normalmente, como se nada tivesse mudado."
)


# ============================================================
# GEMINI LIVE — instrução de sistema principal
# ============================================================
# As duas peças mais longas do projeto ficam em arquivos .md ao lado
# deste, não como constante Python — são multi-seção e ~23 mil
# caracteres somados, o que tornaria este arquivo ilegível como uma
# única string e péssimo de revisar num diff.
#
# Formato dos .md: uma frase por linha (mesmo layout do código
# original), com "## NOME DA SEÇÃO" marcando cada seção — os
# cabeçalhos existem só pra navegação humana, exatamente como os
# comentários "# IDENTIDADE"/"# PERSONALIDADE" no código original:
# são descartados ao carregar, nunca chegam no texto final enviado
# ao modelo.
#
# _carregar() junta as linhas de conteúdo com espaço, NUNCA
# confiando no arquivo já ter espaço no fim de cada linha — isso é
# deliberadamente mais seguro que a concatenação de literais Python
# que este texto tinha antes: lá, uma linha sem o espaço final no
# fim jamava duas palavras em silêncio (bug real, documentado no
# CLAUDE.md); aqui, a junção sempre insere o espaço ela mesma, então
# esse tipo específico de erro não pode mais acontecer só por
# esquecer um espaço no fim da linha.
def _carregar(nome_arquivo):
    linhas = (_PASTA / nome_arquivo).read_text(
        encoding="utf-8"
    ).split("\n")

    partes = [
        linha.strip()
        for linha in linhas
        if linha.strip() and not linha.strip().startswith("##")
    ]

    return "".join(parte + " " for parte in partes)


# Corpo principal da instrução de sistema (identidade, personalidade,
# limites, memória, visão, delegação, encerramento — tudo que não é
# o bloco de autenticação). Termina em "\n\n" de propósito: é o
# separador visual entre a instrução e o contexto de memórias que
# vem concatenado logo depois, em jarvis/gemini/cliente_live.py.
def instrucao_sistema_corpo():
    return _carregar("gemini_live_sistema.md") + "\n\n"


# Bloco de autenticação (a palavra-chave "Coisa") — só deve ser
# concatenado no início de instrucao_sistema quando
# EXIGIR_AUTENTICACAO estiver ligado; a decisão condicional continua
# em cliente_live.py, não aqui (este módulo só entrega o texto).
def bloco_autenticacao():
    return _carregar("gemini_live_autenticacao.md")
