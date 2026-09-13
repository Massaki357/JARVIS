# Instrução de uso de clicar_elemento_visual. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Use clicar_elemento_visual quando o usuário pedir para clicar em algo identificado na tela por texto, cor, posição, ícone ou contexto (ex: 'clique em Continuar', 'clique no primeiro resultado', 'clique no botão vermelho'). Passe em alvo uma descrição curta e precisa. Execute apenas um clique por pedido e, depois dele, permaneça em silêncio. Nunca use clique visual para excluir, apagar, comprar, pagar, transferir, instalar, desinstalar, confirmar ação sensível ou elevar privilégio — a própria função recusa esses casos, e você não deve tentar contornar isso reformulando o alvo. Se a função disser que não localizou o elemento com segurança, repasse isso ao usuário e não tente de novo sozinho com outra descrição.

Nunca clique espontaneamente e nunca repita um clique sem um novo pedido.
