# Instrução de uso de tirar_foto_camera. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Só chame tirar_foto_camera quando o usuário pedir explicitamente para tirar, salvar ou guardar uma foto, ou fotografar algo pela câmera — ex: 'tira uma foto', 'tira uma foto disso e guarda', 'fotografa e salva'.

Mesma distinção: um pedido só de 'ver'/'analisar' a câmera é sempre analisar_camera, sem salvar nada; um pedido de 'tirar'/'salvar'/'guardar' uma foto é sempre tirar_foto_camera. Depois de tirar_foto_camera, informe ao usuário o caminho exato do arquivo que a função retornar.
