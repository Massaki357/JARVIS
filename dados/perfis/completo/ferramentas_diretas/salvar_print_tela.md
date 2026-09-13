# Instrução de uso de salvar_print_tela. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Só chame salvar_print_tela quando o usuário pedir explicitamente para salvar, guardar, tirar e guardar um print, ou capturar e salvar a tela — ex: 'salva um print disso', 'tira um print e guarda', 'captura e salva a tela'.

Não confunda as duas: um pedido só de 'ver'/'analisar' é sempre analisar_tela, sem salvar nada; um pedido de 'salvar'/'guardar' é sempre salvar_print_tela. Depois de salvar_print_tela, informe ao usuário o caminho exato do arquivo que a função retornar.
