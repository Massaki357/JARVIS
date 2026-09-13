# Instrução de uso de analisar_tela. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Só chame analisar_tela quando o usuário pedir explicitamente para ver, analisar, observar ou explicar a tela — essa função só descreve o que está sendo mostrado, nunca salva nada em disco.

Não confunda as duas: um pedido só de 'ver'/'analisar' é sempre analisar_tela, sem salvar nada; um pedido de 'salvar'/'guardar' é sempre salvar_print_tela.
