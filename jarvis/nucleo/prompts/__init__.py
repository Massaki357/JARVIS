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
from datetime import datetime
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

# Retomada de controle: você ficou temporariamente indisponível e o
# cérebro reserva (outra IA) conduziu a conversa em seu lugar por um
# tempo — usado por _anunciar_retomada_gemini em
# jarvis/gemini/cliente_live.py, quando você volta a responder no
# meio de uma chamada. Deliberadamente NÃO pede pra repetir isso em
# voz alta (diferente de ANUNCIO_ESPONTANEO): o usuário já ouviu essa
# parte da conversa de verdade, através do reserva — só o contexto
# precisa chegar até você, em silêncio, pra continuar naturalmente.
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

# Resumo de UMA conversa por voz inteira (não notas antigas — a
# conversa de uma chamada que acabou), pra virar uma memória
# pesquisável numa chamada futura ("como estava aquela conversa
# sobre..."). Usado por consolidacao.salvar_resumo_conversa, chamado
# de jarvis/gemini/cliente_live.py no fim de executar(). Formato de
# resposta fixo (TÍTULO/RESUMO) pra poder ser separado por código sem
# ambiguidade — nunca confiar no modelo pra devolver JSON aqui, texto
# simples com um marcador é mais robusto contra pequenas variações.
CONSOLIDACAO_RESUMO_CONVERSA = (
    "Abaixo está a transcrição de uma conversa por voz entre um "
    "usuário e um assistente pessoal.\n\n"
    "Gere um TÍTULO curto (poucas palavras, específico ao assunto "
    "principal da conversa) e um RESUMO objetivo do que foi "
    "discutido — fatos, decisões, opiniões, qualquer coisa que "
    "ajude a retomar essa conversa numa próxima vez. Não invente "
    "nada que não esteja na transcrição.\n\n"
    "Responda EXATAMENTE neste formato, nada além disso:\n"
    "TÍTULO: <título aqui>\n"
    "RESUMO:\n"
    "<resumo aqui>\n\n"
    "Transcrição:\n{transcricao}"
)


# ============================================================
# ROTEAMENTO_HIERARQUICO — jarvis/roteamento_hierarquico/roteador.py
# (Groq, chat/completions SEM ESTADO — motor de roteamento em duas
# etapas, standalone, ainda não conectado a nenhum dos dois cérebros
# de voz atuais). O catálogo curto em si (nome + resumo de cada
# ferramenta) mora em jarvis/roteamento_hierarquico/catalogo.py, não
# aqui — mesmo tratamento que as descrições de FunctionDeclaration já
# recebem, explicitamente fora desta centralização (ver o topo deste
# arquivo). O que mora aqui são só as duas instruções que ENVOLVEM
# esse catálogo.
# ============================================================

# Etapa 1: prefixo FIXO (junto com {catalogo}, formatado uma única
# vez por chamada — nunca o texto do usuário) para se beneficiar do
# cache automático de prompt da Groq. Pede uma decisão binária:
# responder direto (sem ferramenta nenhuma) ou apontar candidatas
# pelo nome, num formato de marcador simples de analisar — nunca
# JSON, que dependeria de um recurso da API (response_format) ainda
# não confirmado ao vivo pra esse modelo.
ROTEAMENTO_ETAPA1_INSTRUCAO = (
    "Você é o roteador de ferramentas do ALFRED, um assistente "
    "pessoal por voz. Abaixo está o catálogo de ferramentas "
    "disponíveis, agrupado por categoria — cada uma com um resumo "
    "curto do que faz (os detalhes completos e as regras de uso só "
    "aparecem numa etapa seguinte, se for o caso).\n\n"
    "{catalogo}\n\n"
    "Se a mensagem do usuário puder ser respondida sem usar nenhuma "
    "dessas ferramentas, responda normalmente, em português do "
    "Brasil, como o ALFRED responderia.\n\n"
    "Se a mensagem precisar de uma ou mais dessas ferramentas, NÃO "
    "responda normalmente — responda SOMENTE com uma linha no "
    "formato abaixo, sem mais nada antes ou depois:\n"
    "FERRAMENTAS: nome_da_ferramenta, outro_nome\n\n"
    "Use no máximo 3 nomes, e somente nomes que existem no catálogo "
    "acima, exatamente como escritos. Nunca invente um nome. Na "
    "dúvida entre responder direto ou apontar uma ferramenta, "
    "prefira responder direto."
)

# Etapa 2: só é montada (e só é chamada) quando a etapa 1 apontou
# candidatas. {ferramentas} aqui é a lista de nomes candidatos, só
# pra dar contexto ao modelo sobre por que aquele schema específico
# foi carregado — o schema completo em si vai no parâmetro "tools" da
# chamada, não neste texto.
ROTEAMENTO_ETAPA2_INSTRUCAO = (
    "Você é o ALFRED, um assistente pessoal por voz. Com base no "
    "pedido do usuário, monte a chamada de função apropriada dentre "
    "estas ferramentas: {ferramentas}. Preencha os parâmetros com "
    "exatamente o que o usuário disse, sem inventar nem completar "
    "informação que faltou. Se, ao ver os detalhes completos, "
    "nenhuma dessas ferramentas realmente servir para o pedido, "
    "responda normalmente em texto em vez de chamar uma função."
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


# Data e hora local, injetada no fim da instrução de sistema. Vem
# do JARVIS COMPLETO, onde era um f-string dentro da própria
# instrucao_sistema: sem isso o modelo não tem como interpretar
# "hoje", "amanhã" ou um dia da semana ao criar um evento de agenda.
# É função, e não constante, justamente porque precisa ser avaliada
# no início de CADA chamada, não uma vez no import do módulo.
def contexto_data_hora():
    return (
        "Data e hora local atual: "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}. "
    )


# Bloco de autenticação (a palavra-chave "Coisa") — só deve ser
# concatenado no início de instrucao_sistema quando
# EXIGIR_AUTENTICACAO estiver ligado; a decisão condicional continua
# em cliente_live.py, não aqui (este módulo só entrega o texto).
def bloco_autenticacao():
    return _carregar("gemini_live_autenticacao.md")
