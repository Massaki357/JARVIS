# Instrução de uso de analisar_camera. Lida pelo cérebro com
# ler_instrucao_ferramenta antes do primeiro uso na conversa.
# Linhas com # não são entregues ao modelo.

Só chame analisar_camera quando o usuário pedir explicitamente para ver, analisar, observar ou explicar a câmera, webcam ou algo mostrado nela — só descreve, nunca salva nada. Se o usuário pedir pra tirar/salvar/guardar uma foto, use tirar_foto_camera em vez desta.

Mesma distinção: um pedido só de 'ver'/'analisar' a câmera é sempre analisar_camera, sem salvar nada; um pedido de 'tirar'/'salvar'/'guardar' uma foto é sempre tirar_foto_camera.

abrir_camera e fechar_camera são diferentes de analisar_camera/tirar_foto_camera: em vez de um único frame, abrem/fecham uma JANELA com o vídeo da webcam atualizado continuamente.
