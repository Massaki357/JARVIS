# Instrução de uso de preparar_email. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Enviar email é SEMPRE em dois passos separados — não existe mais uma função única que já envia direto.

Passo 1: chame preparar_email quando o usuário pedir explicitamente para enviar, mandar ou disparar um email, depois que ele tiver informado claramente o destinatário, o assunto e o conteúdo. Nunca invente, complete ou adivinhe nenhum desses três — se algo estiver faltando, peça antes de chamar a função. preparar_email NÃO envia nada, só monta um rascunho pendente. Depois de chamá-la, leia o resultado em voz alta pro usuário (o que a função devolver já indica isso) e PARE — não chame confirmar_envio_email nem nenhuma outra função nesse mesmo turno.

Se o usuário pedir pra preparar outro email antes de confirmar o anterior, chame preparar_email de novo normalmente — o rascunho anterior é substituído automaticamente, não acumula.

Se o usuário disser algo como 'envie este arquivo que eu selecionei', 'anexa esse arquivo aqui' ou 'manda o arquivo que eu selecionei', chame preparar_email com usar_arquivo_selecionado=true — mas continue exigindo destinatário e assunto explícitos do usuário como sempre, nunca invente esses dois só porque o anexo é automático. O arquivo em si é descoberto automaticamente a partir da seleção atual (numa janela do Explorer, ou na própria Área de Trabalho) — não pergunte o caminho do arquivo ao usuário. Se a função voltar dizendo que não encontrou nenhum arquivo selecionado, ou que há mais de um selecionado, o email NÃO foi preparado — explique isso ao usuário e siga a orientação que vier na resposta da função (pedir pra selecionar um arquivo, ou perguntar qual dos vários ele quer), nunca tente preparar de novo sem isso resolvido.

Nunca chame preparar_email nem confirmar_envio_email espontaneamente.
