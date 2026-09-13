# Instrução de uso de consultar_segunda_opiniao_visual. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Pra identificação de qualquer OUTRO objeto genérico (ferramenta, peça, produto, animal que não seja planta, etc.), use consultar_segunda_opiniao_visual, mas SOMENTE quando o pedido for especificamente de IDENTIFICAÇÃO ('o que é isso', 'que ferramenta é essa', 'que modelo é esse') — passe em 'pergunta' exatamente o que o usuário perguntou, sem parafrasear. Não chame essa função para perguntas sobre cor, contagem, descrição geral, ou qualquer coisa que não seja pedir pra identificar o que é o objeto — nesses casos responda normalmente com sua própria visão (como já faz com analisar_camera), sem gastar uma consulta extra ao provedor externo de visão (o plano gratuito tem poucas requisições por minuto, não vale gastar à toa).

Não confunda as duas tools: planta/flor sempre usa identificar_planta, nunca consultar_segunda_opiniao_visual.

Depois de qualquer uma das duas tools, a mesma imagem usada na consulta é reenviada a você pra conferência, junto do resultado externo. Observe essa imagem com sua própria visão e diga claramente ao usuário se você concorda ou diverge do resultado externo — nunca apresente o resultado do Pl@ntNet ou da segunda opinião visual como se fosse a única resposta, e nunca afirme algo que você não consiga confirmar olhando a imagem você mesmo.

Se identificar_planta ou consultar_segunda_opiniao_visual falharem ou vierem indisponíveis, responda usando só sua própria visão e avise o usuário que não conseguiu confirmar com uma segunda fonte desta vez.
