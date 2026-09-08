# Todo texto de instrução hardcoded enviado a algum modelo (Gemini,
# Groq, Cerebras, OpenAI, Mistral) neste projeto vive aqui —
# centralizado numa tarefa dedicada, para reaproveitamento e
# organização, sem alterar nenhum texto final que chega a cada
# modelo (cada extração foi verificada byte a byte — hash sha256 do
# valor antigo comparado contra o novo — antes de qualquer coisa ser
# movida).
#
# ORGANIZAÇÃO POR CÉREBRO: cada prompt vira um arquivo .md dentro de
# uma subpasta por cérebro de voz (a mesma divisão de
# jarvis/cerebro/): "gemini/" (só Gemini Live), "openai/" (só OpenAI
# Realtime — vazia hoje, nenhum prompt é exclusivo dele) e "local/"
# (só o alfred-server / voz_local, que não recebe imagem nativa e por
# isso tem seus próprios prompts de descrição visual). Um prompt
# reaproveitado por mais de um cérebro (a instrução de sistema comum
# ao Gemini Live e ao OpenAI Realtime, os textos de tool result de
# pacotes que funcionam com qualquer cérebro ativo, etc.) mora em
# "geral/" em vez de duplicado em cada subpasta. Isso é o que dá
# controle real por cérebro: editar um arquivo de "gemini/" nunca
# afeta o OpenAI Realtime, e vice-versa.
#
# Cada arquivo .md contém o texto FINAL exato (com os mesmos
# marcadores "{campo}" que antes existiam na constante Python, para
# o mesmo .format() de sempre), sem nenhuma linha de cabeçalho nem
# transformação de espaçamento: _carregar_arquivo() só lê o arquivo e
# remove a quebra de linha final que o editor deixou, byte a byte
# igual ao que a constante Python continha.
#
# O QUE NÃO ENTRA AQUI: uma linha de prompt que tem uma variável
# espalhada no meio da frase (ex.: f"Você é {obter_nome_jarvis()}, o
# assistente pessoal..." em jarvis/cerebro/voz_local/contexto.py)
# continua como f-string no próprio arquivo de código — extrair só
# esse pedaço não ajudaria a editar o prompt sem tocar em código, e
# quebraria a frase ao meio. Só o texto FIXO ao redor dessas linhas
# (quando há algum) é que vira arquivo .md.
#
# Os dois prompts realmente grandes e multi-seção (a instrução de
# sistema completa da sessão de voz e o bloco de autenticação)
# também não viram string Python: são arquivos .md, porque uma
# constante de ~22 mil caracteres numa linha só seria ilegível e
# impossível de revisar num diff. A instrução de sistema em si não
# mora nesta pasta (ver a seção "GEMINI LIVE — instrução de sistema
# principal" mais abaixo); o bloco de autenticação mora em
# "geral/autenticacao.md", porque tanto o Gemini Live quanto o OpenAI
# Realtime o usam.
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
# _carregar_prosa() logo abaixo pra substituir toda ocorrência
# literal de "ALFRED" no .md da instrução de sistema/autenticação
# pelo nome que o usuário escolheu.
from jarvis.nucleo.config import obter_nome_jarvis

_PASTA = Path(__file__).resolve().parent


# Carrega um prompt curto/médio de um .md desta pasta (organizado por
# cérebro — ver o comentário no topo do arquivo) devolvendo o texto
# EXATO do arquivo, sem nenhuma transformação além de remover a
# quebra de linha final que sobra do editor. Diferente de
# _carregar_prosa() abaixo: aqui as quebras de linha internas (que
# alguns prompts usam de propósito, como separador de parágrafo) são
# preservadas literalmente, nunca substituídas por espaço — e não há
# substituição de "ALFRED", porque nenhum destes prompts menciona o
# nome do assistente.
def _carregar_arquivo(caminho_relativo):
    return (_PASTA / caminho_relativo).read_text(
        encoding="utf-8"
    ).rstrip("\n")


# ============================================================
# GEMINI + OPENAI (geral/) — jarvis/cerebro/gemini/cliente_live.py e
# jarvis/cerebro/openai_realtime/cliente_realtime.py
# Prompts pontuais enviados durante a sessão, idênticos nos dois
# cérebros de sessão (a instrução de sistema completa fica no fim
# deste arquivo). Ficam em geral/ e não em gemini/ ou openai/ porque
# os DOIS clientes chamam exatamente a mesma constante.
# ============================================================

# Anúncio espontâneo: o worker "fala" algo sem o usuário ter
# perguntado nada agora (aviso de permissão remota, resultado de um
# comando administrativo confirmado fora da conversa, fim do timeout
# de inatividade, etc.) — usado por _enviar_anuncio_espontaneo, e
# reaproveitado por rede_jarvis/admin_terminal via callback_falar.
ANUNCIO_ESPONTANEO = _carregar_arquivo("geral/anuncio_espontaneo.md")

# Retomada de controle: você ficou temporariamente indisponível e o
# cérebro reserva (outra IA) conduziu a conversa em seu lugar por um
# tempo — usado por _anunciar_retomada_gemini em
# jarvis/cerebro/gemini/cliente_live.py, quando você volta a responder no
# meio de uma chamada. Deliberadamente NÃO pede pra repetir isso em
# voz alta (diferente de ANUNCIO_ESPONTANEO): o usuário já ouviu essa
# parte da conversa de verdade, através do reserva — só o contexto
# precisa chegar até você, em silêncio, pra continuar naturalmente.
ANALISE_IMAGEM_PONTUAL = _carregar_arquivo("geral/analise_imagem_pontual.md")

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
SAUDACAO_ATIVACAO_POR_VOZ = _carregar_arquivo(
    "geral/saudacao_ativacao_por_voz.md"
)


# ============================================================
# GEMINI (gemini/) — jarvis/cerebro/gemini/cliente_live.py
# Prompt exclusivo do Gemini Live: o OpenAI Realtime e o voz_local
# não fazem esse cruzamento de segunda opinião visual.
# ============================================================

# Cruzamento de segunda opinião visual: reenvia a MESMA imagem já
# usada numa consulta externa (Pl@ntNet ou Mistral) pedindo pro
# Gemini olhar com a própria visão e comparar, em vez de só repassar
# o resultado externo sem checagem — usado por
# enviar_imagem_para_cruzamento (identificar_planta e
# consultar_segunda_opiniao_visual).
CRUZAMENTO_SEGUNDA_OPINIAO = _carregar_arquivo(
    "gemini/cruzamento_segunda_opiniao.md"
)


# ============================================================
# ENVIO DE ARQUIVO PELA UI (geral/) — jarvis/ui/janela_envio_arquivo.py
# Entram na sessão ativa via <Worker>.enviar_texto_da_ui /
# enviar_imagem_da_ui — os três cérebros (Gemini Live, OpenAI
# Realtime, voz_local) implementam os dois métodos, então ficam em
# geral/. Ver o comentário sobre chat_jarvis no CLAUDE.md pra por que
# esse caminho usa um mecanismo diferente do resto (send_realtime_input,
# não send_client_content, no caso do Gemini Live).
# ============================================================

CONTEXTO_IMAGEM_ENVIADA = _carregar_arquivo(
    "geral/contexto_imagem_enviada.md"
)

CONTEXTO_ARQUIVO_ENVIADO = _carregar_arquivo(
    "geral/contexto_arquivo_enviado.md"
)


# ============================================================
# DELEGACAO_IA (geral/) — jarvis/pacotes/delegacao_ia/roteador.py
# (Groq/Cerebras/OpenAI, por trás de delegar_tarefa) — textos
# devolvidos como resultado da tool a QUALQUER cérebro ativo, não
# prompts para os provedores em si (provedores.py manda o "conteudo"
# cru, sem nenhuma instrução hardcoded própria — ver a nota em
# _chamar_completions).
# ============================================================

DELEGACAO_INDISPONIVEL = _carregar_arquivo("geral/delegacao_indisponivel.md")

DELEGACAO_SEGUNDA_OPINIAO_INDISPONIVEL = _carregar_arquivo(
    "geral/delegacao_segunda_opiniao_indisponivel.md"
)

DELEGACAO_SEGUNDA_OPINIAO_RESULTADO = _carregar_arquivo(
    "geral/delegacao_segunda_opiniao_resultado.md"
)


# ============================================================
# DESCRICAO_VISUAL (local/) — jarvis/pacotes/descricao_visual/
# (descreve tela/câmera em texto, exclusivo do modo de voz local —
# é o único cérebro sem entrada de imagem nativa)
# ============================================================

# Instrução de sistema da chamada de visão. Pede descrição objetiva
# porque o texto devolvido é falado de volta ao usuário: uma resposta
# longa demais vira um monólogo que ele não pediu.
DESCRICAO_VISUAL_INSTRUCAO = _carregar_arquivo(
    "local/descricao_visual_instrucao.md"
)

# Pergunta usada quando o usuário só pediu para olhar, sem perguntar
# nada específico.
DESCRICAO_VISUAL_PERGUNTA_PADRAO = _carregar_arquivo(
    "local/descricao_visual_pergunta_padrao.md"
)

# Devolvido quando a consulta falha. Diferente da convenção de
# identificacao_visual (que instrui o cérebro a responder com a
# própria visão): aqui a descrição É a resposta do turno, então não
# há visão própria para usar como alternativa — a falha precisa ser
# dita ao usuário.
DESCRICAO_VISUAL_INDISPONIVEL = _carregar_arquivo(
    "local/descricao_visual_indisponivel.md"
)


# ============================================================
# CONTEXTO (local/) — jarvis/cerebro/voz_local/contexto.py
# O alfred-server não guarda sessão (ver o comentário no topo de
# contexto.py): o JARVIS monta esse contexto e manda pronto a cada
# chamada. A linha de identidade em si (com o nome configurável no
# meio da frase) continua como f-string em contexto.py — só o texto
# fixo abaixo dela vem daqui.
# ============================================================

# Introduz a lista de fatos de memória relevantes ao turno atual.
CONTEXTO_MEMORIAS_INTRO = _carregar_arquivo("local/contexto_memorias_intro.md")


# ============================================================
# IDENTIFICACAO_VISUAL (geral/) — jarvis/pacotes/identificacao_visual/
# mistral_vision_client.py (Mistral, com entrada de imagem) — a
# segunda opinião funciona com qualquer cérebro ativo, daí geral/.
# ============================================================

# Pergunta padrão quando o usuário não deu uma pergunta específica —
# essa sim é enviada de verdade ao provedor de visão, junto com a
# imagem (as outras duas constantes desta seção voltam pro cérebro
# como tool result).
VISAO_PERGUNTA_PADRAO = _carregar_arquivo("geral/visao_pergunta_padrao.md")

# Texto devolvido ao cérebro quando a consulta de segunda opinião
# falha por qualquer motivo — instrui a responder só com a própria
# visão. {provedor} porque a fonte deixou de ser fixa: quem responde
# é o provedor oposto ao cérebro de voz ativo (Mistral no modo Gemini,
# Gemini nos modos openai/local), a menos que DESCRICAO_VISUAL_PROVEDOR
# force um — ver jarvis/pacotes/identificacao_visual/config.py. Dizer o
# nome errado seria pior do que não dizer nenhum.
VISAO_INDISPONIVEL = _carregar_arquivo("geral/visao_indisponivel.md")


# ============================================================
# MEMORIA_OBSIDIAN (geral/) — jarvis/pacotes/memoria_obsidian/consolidacao.py
# (Gemini, chamada de texto simples — a consolidação em background
# das notas arquivadas, sem voz nem UI, independente de qual cérebro
# de voz está ativo no momento).
# ============================================================

CONSOLIDACAO_RESUMO_ARQUIVO = _carregar_arquivo(
    "geral/consolidacao_resumo_arquivo.md"
)

# Resumo de UMA conversa por voz inteira (não notas antigas — a
# conversa de uma chamada que acabou), pra virar uma memória
# pesquisável numa chamada futura ("como estava aquela conversa
# sobre..."). Usado por consolidacao.salvar_resumo_conversa, chamado
# de jarvis/cerebro/gemini/cliente_live.py no fim de executar(). Formato de
# resposta fixo (TÍTULO/RESUMO) pra poder ser separado por código sem
# ambiguidade — nunca confiar no modelo pra devolver JSON aqui, texto
# simples com um marcador é mais robusto contra pequenas variações.
CONSOLIDACAO_RESUMO_CONVERSA = _carregar_arquivo(
    "geral/consolidacao_resumo_conversa.md"
)


# ============================================================
# ROTEAMENTO_HIERARQUICO (geral/) — jarvis/roteamento_hierarquico/roteador.py
# (Groq, chat/completions SEM ESTADO — motor de roteamento em duas
# etapas, standalone, ainda não conectado a nenhum dos cérebros de
# voz atuais — por isso geral/, e não uma subpasta de cérebro
# específico). O catálogo curto em si (nome + resumo de cada
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
ROTEAMENTO_ETAPA1_INSTRUCAO = _carregar_arquivo(
    "geral/roteamento_etapa1_instrucao.md"
)

# Etapa 2: só é montada (e só é chamada) quando a etapa 1 apontou
# candidatas. {ferramentas} aqui é a lista de nomes candidatos, só
# pra dar contexto ao modelo sobre por que aquele schema específico
# foi carregado — o schema completo em si vai no parâmetro "tools" da
# chamada, não neste texto.
ROTEAMENTO_ETAPA2_INSTRUCAO = _carregar_arquivo(
    "geral/roteamento_etapa2_instrucao.md"
)


# ============================================================
# GEMINI LIVE — instrução de sistema principal
# ============================================================
# A instrução de sistema completa (corpo do perfil + bloco de
# autenticação) NÃO vira constante Python — juntas somam ~23 mil
# caracteres, o que tornaria este arquivo ilegível como uma única
# string e péssimo de revisar num diff. O corpo mora no perfil ativo
# (dados/perfis/<slug>/sistema.md); o bloco de autenticação mora
# aqui mesmo, em geral/autenticacao.md (ver mais abaixo por quê).
#
# Formato dos .md: uma frase por linha (mesmo layout do código
# original), com "## NOME DA SEÇÃO" marcando cada seção — os
# cabeçalhos existem só pra navegação humana, exatamente como os
# comentários "# IDENTIDADE"/"# PERSONALIDADE" no código original:
# são descartados ao carregar, nunca chegam no texto final enviado
# ao modelo.
#
# _carregar_prosa() junta as linhas de conteúdo com espaço, NUNCA
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
# Separada de _carregar_prosa() porque o prompt de sistema não vem mais de
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


def _carregar_prosa(caminho_relativo):
    return _montar_texto(
        (_PASTA / caminho_relativo).read_text(encoding="utf-8")
    )


# Corpo principal da instrução de sistema (identidade, personalidade,
# limites, memória, visão, delegação, encerramento — tudo que não é
# o bloco de autenticação). Termina em "\n\n" de propósito: é o
# separador visual entre a instrução e o contexto de memórias que
# vem concatenado logo depois, em jarvis/cerebro/gemini/cliente_live.py.
#
# O texto NÃO mora mais nesta pasta: ele é o sistema.md do perfil,
# em dados/perfis/<slug>/sistema.md. O arquivo
# gemini_live_sistema.md que ficava aqui foi MOVIDO, byte a byte, pra
# dados/perfis/completo/sistema.md — o perfil padrão. Sem slug, esta
# função devolve o corpo desse perfil padrão, que é exatamente o
# texto que o projeto sempre enviou.
#
# O bloco de autenticação (geral/autenticacao.md) continua aqui de
# propósito: ele não é específico de perfil nenhum, é a trava de
# segurança que vale para todos os cérebros — Gemini Live e OpenAI
# Realtime.
def instrucao_sistema_corpo(slug_perfil=None, texto_bruto=None):
    # texto_bruto vem preenchido quando quem chama já resolveu o
    # perfil (perfis.preparar_chamada, usado pelos dois clientes de
    # voz): assim o arquivo é lido UMA vez por chamada, e o caminho de
    # falha — perfil ilegível caindo para o prompt do padrão — fica
    # num lugar só, em vez de repetido aqui.
    if texto_bruto is not None:
        return _montar_texto(texto_bruto) + "\n\n"

    from jarvis.nucleo import perfis

    slug = slug_perfil or perfis.SLUG_PADRAO

    return _montar_texto(
        perfis.preparar_chamada(slug)["prompt_bruto"]
    ) + "\n\n"


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
# em cliente_live.py/cliente_realtime.py, não aqui (este módulo só
# entrega o texto). Fica em geral/ porque os dois cérebros de sessão
# o usam.
def bloco_autenticacao():
    return _carregar_prosa("geral/autenticacao.md")


# ============================================================
# PERFIS (geral/) — jarvis/nucleo/perfis/geracao.py
# Criação de um perfil a partir de uma descrição em texto livre —
# roteada por delegar_para_cerebro_configurado, não por um cérebro de
# voz específico, daí geral/.
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
CRIACAO_PERFIL = _carregar_arquivo("geral/criacao_perfil.md")
