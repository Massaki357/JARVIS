# Instrução de uso de confirmar_envio_email. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Enviar email é SEMPRE em dois passos separados — não existe mais uma função única que já envia direto.

Passo 2: só depois de ouvir a resposta do usuário na fala seguinte — depois de ele ter escutado a leitura do rascunho e respondido de verdade — chame confirmar_envio_email com confirmar=true (se ele confirmou, ex: 'sim', 'pode mandar', 'envia') ou confirmar=false (se ele negou ou pediu pra cancelar, ex: 'não', 'cancela', 'espera'). Nunca chame confirmar_envio_email com confirmar=true sem ter literalmente ouvido essa resposta afirmativa — não assuma concordância, não confirme sozinho, não repita um envio antigo.

Nunca chame preparar_email nem confirmar_envio_email espontaneamente.
