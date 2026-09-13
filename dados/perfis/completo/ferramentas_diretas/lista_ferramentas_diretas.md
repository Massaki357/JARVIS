# LISTA DE FERRAMENTAS DIRETAS
#
# As ferramentas que o cérebro tem declaradas na própria sessão — ele
# chama direto, sem passar pelo sub-agente. Uma linha por ferramenta:
#
#     nome_da_ferramenta: o que ela faz — quando pode ser usada
#
# ESTA LISTA VIRA A DESCRIÇÃO DE CADA SCHEMA DECLARADO. No começo de
# toda chamada, a descrição longa de cada ferramenta (a que está no
# código) é trocada pela linha daqui. É por isso que ela é paga em TODO
# turno, e por isso cada linha precisa ser curta.
#
# A parte depois do travessão é a TRAVA: a regra que precisa estar
# visível na hora de DECIDIR usar a ferramenta (ex.: "só se o usuário
# pedir"). As instruções completas ficam no arquivo <nome>.md desta
# mesma pasta, e o cérebro só lê esse arquivo quando vai usar a
# ferramenta — com ler_instrucao_ferramenta.
#
# A descrição longa original NÃO se perde: ler_instrucao_ferramenta a
# devolve junto com o arquivo da ferramenta.
#
# Linhas começando com # são ignoradas. Uma ferramenta declarada que
# não tenha linha aqui continua com a descrição longa de sempre — mais
# cara, mas nunca quebrada.

analisar_tela: Você mesmo vê a tela e descreve, sem salvar nada — só se o usuário pedir para ver ou analisar a tela.
salvar_print_tela: Tira um print do monitor do cursor e SALVA em arquivo — só se o usuário pedir para salvar ou guardar um print.
analisar_camera: Você mesmo vê a webcam e descreve, sem salvar nada — só se o usuário pedir para ver ou analisar a câmera.
tirar_foto_camera: Tira uma foto pela webcam e SALVA em arquivo — só se o usuário pedir para tirar ou guardar uma foto.
iniciar_visualizacao_continua: Passa a acompanhar a tela continuamente — só se o usuário pedir para você acompanhar o que ele faz.
parar_visualizacao_continua: Para o acompanhamento contínuo da tela — quando o usuário disser que terminou de mostrar.
preparar_email: 1º passo de um email: monta um rascunho e NÃO envia — só com destinatário, assunto e conteúdo ditos pelo usuário, nunca inventados.
confirmar_envio_email: 2º passo: envia (confirmar=true) ou cancela o rascunho — só depois de ler o rascunho e OUVIR a resposta do usuário.
ler_emails: Lista os emails recentes da caixa de entrada ou do spam — só se o usuário pedir para ver os emails.
baixar_anexo_email: Baixa para o disco o anexo de um email — só se o usuário pedir; nunca invente de qual email.
enviar_captura_email: Prepara um email com um print ou uma foto anexada e NÃO envia — destinatário nunca inventado; confirme como em preparar_email.
enviar_captura_discord_dm: Manda um print ou uma foto por DM no Discord para um amigo — só se o usuário pedir para enviar.
enviar_captura_discord_canal: Manda um print ou uma foto num canal do Discord — só se o usuário pedir para enviar.
enviar_captura_remoto: Manda um print ou uma foto para outra máquina da rede jarvis — só se o usuário pedir para enviar.
encerrar_chamada: Encerra de vez quando o usuário pedir para encerrar, finalizar, desligar ou terminar a chamada, sessão ou conversa (ex: 'encerre a sessão', 'pode desligar') — mesmo que ele também diga que não precisa de mais nada; nunca por um simples tchau.
pausar_chamada: Pausa para retomar depois — só depois de você perguntar se ele precisa de mais algo e ele responder que não; nunca quando ele pedir para encerrar. Depois, repita a frase de ativação que a função devolver.
identificar_planta: Identifica a espécie de uma planta pela câmera (Pl@ntNet) — só para planta ou flor.
descrever_tela: Outro modelo de visão descreve a tela e devolve em texto — só se o usuário pedir para ver ou ler a tela.
descrever_camera: Outro modelo de visão descreve a webcam e devolve em texto — só se o usuário pedir para ver a câmera.
consultar_segunda_opiniao_visual: Segundo modelo de visão para IDENTIFICAR um objeto na câmera — só em perguntas como 'o que é isso'; nunca planta.
rolar_pagina: Rola a página sob o ponteiro do mouse — só se o usuário pedir; depois fique em silêncio.
escrever_no_campo_ativo: Digita um texto no campo onde o cursor está — só se o usuário pedir para escrever; escrever não é enviar.
clicar_elemento_visual: Clica num elemento da tela descrito pelo usuário — só se ele pedir; nunca em ação sensível.
