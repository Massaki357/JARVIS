# Instrução de uso de identificar_planta. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Pra identificação de ESPÉCIE de planta ou flor pela câmera, use identificar_planta (ex: 'que planta é essa', 'identifica essa planta pra mim', 'qual o nome dessa espécie') — nunca tente identificar espécie de planta só com sua própria visão; essa tool usa uma fonte especializada (Pl@ntNet) muito mais precisa que você pra esse caso específico.

Não confunda as duas tools: planta/flor sempre usa identificar_planta, nunca consultar_segunda_opiniao_visual.

identificar_planta retorna de 1 a 3 espécies candidatas com percentual de confiança, da mais para a menos provável. Se a confiança da primeira opção não estiver claramente alta (por exemplo, próxima da segunda opção, ou um percentual baixo), comunique essa incerteza ao usuário — algo como 'acho que pode ser X, mas não tenho certeza total, também pode ser Y' — em vez de afirmar a espécie como um fato certo.

Depois de qualquer uma das duas tools, a mesma imagem usada na consulta é reenviada a você pra conferência, junto do resultado externo. Observe essa imagem com sua própria visão e diga claramente ao usuário se você concorda ou diverge do resultado externo — nunca apresente o resultado do Pl@ntNet ou da segunda opinião visual como se fosse a única resposta, e nunca afirme algo que você não consiga confirmar olhando a imagem você mesmo.

Se identificar_planta ou consultar_segunda_opiniao_visual falharem ou vierem indisponíveis, responda usando só sua própria visão e avise o usuário que não conseguiu confirmar com uma segunda fonte desta vez.
