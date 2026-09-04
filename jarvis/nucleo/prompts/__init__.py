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

# Nome de identidade configurável (jarvis/nucleo/config.py::
# obter_nome_jarvis, .env NOME_JARVIS, padrão "ALFRED") — usado por
# _carregar() logo abaixo pra substituir toda ocorrência literal de
# "ALFRED" nos .md desta pasta pelo nome que o usuário escolheu.
from jarvis.nucleo.config import obter_nome_jarvis

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

# Enviada por executar() logo depois de conectar — SOMENTE quando a
# chamada foi iniciada pela ativação por voz (a frase configurada em
# jarvis/pacotes/ativacao_voz/config.py::NOME_ATIVACAO), nunca pelo botão
# manual. Isso é deliberado: uma saudação falada em TODA chamada já foi
# tentada antes e removida por ser lenta demais (ver "Local 'call
# started' beep" no CLAUDE.md — dependia de um round-trip completo só
# pra dizer "Chamada iniciada."). Aqui a mesma lentidão existe, mas o
# trade-off é diferente: o usuário literalmente acabou de chamar o
# assistente pelo nome/frase de ativação, então uma resposta faz
# sentido de novo — só que restrita a este caso específico, sem trazer
# de volta o atraso pra toda chamada iniciada manualmente.
SAUDACAO_ATIVACAO_POR_VOZ = (
    "[SISTEMA] O usuário acabou de te chamar agora, dizendo a frase "
    "de ativação por voz. Cumprimente-o brevemente, perguntando como "
    "pode ajudar — por exemplo algo como 'Como posso ajudar?' — "
    "antes de qualquer outra coisa."
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
#
# Depois de montar o texto, toda ocorrência literal de "ALFRED" (o
# nome de identidade original, escrito à mão nos .md) é trocada pelo
# nome configurado em NOME_JARVIS (.env) — é assim que "Seu nome é
# ALFRED." e as demais menções ao nome viram o nome que o usuário
# escolheu, sem precisar editar cada .md na mão. Aplicado aqui, uma
# vez, em vez de em cada .md separadamente: cobre qualquer arquivo
# futuro carregado por esta função automaticamente. Seguro como troca
# literal (não regex) porque "ALFRED" não aparece como pedaço de outra
# palavra em nenhum dos .md desta pasta (confirmado antes de fazer
# esta troca).
# Aplica a montagem do texto final a partir do conteúdo BRUTO de um
# arquivo .md deste formato: descarta linhas em branco e cabeçalhos
# "##" (navegação humana, nunca parte do texto enviado ao modelo),
# junta o resto inserindo o espaço separador ela mesma, e troca
# "ALFRED" pelo nome configurado.
#
# Separada de _carregar() porque o prompt de sistema não vem mais de
# um arquivo desta pasta: ele mora no perfil ativo
# (dados/perfis/<slug>/sistema.md, ver jarvis/nucleo/perfis/). As
# duas origens precisam passar pela MESMA montagem, senão o texto que
# chega ao modelo muda dependendo de onde o arquivo estava.
def _montar_texto(texto_bruto):
    linhas = str(texto_bruto or "").split("\n")

    partes = [
        linha.strip()
        for linha in linhas
        if linha.strip() and not linha.strip().startswith("##")
    ]

    texto = "".join(parte + " " for parte in partes)

    return texto.replace("ALFRED", obter_nome_jarvis())


def _carregar(nome_arquivo):
    return _montar_texto(
        (_PASTA / nome_arquivo).read_text(encoding="utf-8")
    )


# Corpo principal da instrução de sistema (identidade, personalidade,
# limites, memória, visão, delegação, encerramento — tudo que não é
# o bloco de autenticação). Termina em "\n\n" de propósito: é o
# separador visual entre a instrução e o contexto de memórias que
# vem concatenado logo depois, em jarvis/gemini/cliente_live.py.
#
# O texto NÃO mora mais nesta pasta: ele é o sistema.md do perfil,
# em dados/perfis/<slug>/sistema.md. O arquivo
# gemini_live_sistema.md que ficava aqui foi MOVIDO, byte a byte, pra
# dados/perfis/completo/sistema.md — o perfil padrão. Sem slug, esta
# função devolve o corpo desse perfil padrão, que é exatamente o
# texto que o projeto sempre enviou.
#
# O bloco de autenticação (gemini_live_autenticacao.md) continua
# aqui de propósito: ele não é específico de perfil nenhum, é a trava
# de segurança que vale para todos.
def instrucao_sistema_corpo(slug_perfil=None):
    from jarvis.nucleo import perfis

    slug = slug_perfil or perfis.SLUG_PADRAO

    return _montar_texto(perfis.texto_sistema(slug)) + "\n\n"


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


# ============================================================
# PERFIS — jarvis/nucleo/perfis/geracao.py
# Criação de um perfil a partir de uma descrição em texto livre.
# ============================================================

# Pedido enviado ao modelo na criação de um perfil. Três campos
# preenchidos por geracao.py: {descricao} (o texto livre do usuário),
# {catalogo} (nome + resumo de uma linha de TODAS as ferramentas
# registradas, montado a partir do catálogo real do projeto) e
# {nome_assistente}.
#
# A resposta é exigida em JSON com esquema fixo — não é uma sugestão
# de formato, é validada em código: nome de ferramenta inexistente é
# ERRO, nunca passa em silêncio (ver geracao.interpretar_resposta).
#
# Note o que este prompt NÃO faz: ele não sabe quais ferramentas são
# sensíveis, e não deveria. A separação entre o que entra direto e o
# que precisa da confirmação do usuário acontece DEPOIS, em código
# (jarvis/nucleo/perfis/sensiveis.py). Pedir ao modelo que "não
# escolha ferramenta perigosa" seria confiar a trava de segurança a
# uma instrução de texto; do jeito que está, o modelo pode escolher o
# que quiser que nada sensível entra sem o usuário aprovar item a
# item.
CRIACAO_PERFIL = (
    "Você configura perfis de uso de um assistente de voz chamado "
    "{nome_assistente}, que roda no computador do usuário.\n\n"
    "Um PERFIL é formado por duas coisas: um prompt de sistema, que "
    "define como o assistente se comporta naquele cenário, e o "
    "subconjunto de ferramentas que ele pode usar ali.\n\n"
    "O usuário descreveu o perfil que quer assim:\n\n"
    "\"\"\"\n{descricao}\n\"\"\"\n\n"
    "Estas são TODAS as ferramentas que existem no projeto. Você só "
    "pode escolher nomes desta lista, copiados exatamente como estão "
    "escritos aqui:\n\n"
    "{catalogo}\n\n"
    "Responda SOMENTE com um objeto JSON, sem texto antes ou depois, "
    "com exatamente estes três campos:\n\n"
    "- \"nome\": um nome curto de exibição para o perfil, no máximo 40 "
    "caracteres, em português do Brasil. Sem aspas, sem emoji.\n"
    "- \"ferramentas\": uma lista com os nomes das ferramentas que "
    "esse perfil deve poder usar. Escolha só o que o cenário descrito "
    "realmente precisa — um perfil focado é melhor que um perfil com "
    "tudo. Se o cenário não pedir nenhuma ferramenta, devolva uma "
    "lista vazia.\n"
    "- \"prompt_sistema\": o texto do prompt de sistema desse perfil, "
    "em português do Brasil, escrito na segunda pessoa (falando COM o "
    "assistente, como em \"Você é...\"). Descreva o papel, o tom, o "
    "que ele deve e o que não deve fazer nesse cenário, e como usar "
    "as ferramentas escolhidas. Não repita a lista de ferramentas "
    "como um índice: explique o comportamento. Organize em seções "
    "usando linhas que comecem com \"## \" como título — essas linhas "
    "são só navegação para quem lê o arquivo e não são enviadas ao "
    "modelo depois.\n\n"
    "Nunca invente um nome de ferramenta que não esteja na lista "
    "acima."
)
