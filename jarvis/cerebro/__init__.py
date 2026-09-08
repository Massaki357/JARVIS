"""
Os cérebros de voz do ALFRED — um subpacote por modo de voz.

Cada um implementa a MESMA API pública (os sete sinais, o construtor
(session_handle, transcricao_inicial, ativado_por_voz, slug_perfil),
parar, solicitar_analise_tela, solicitar_analise_camera,
enviar_texto_da_ui, enviar_imagem_da_ui, transcricao_conversa e
slug_perfil). É essa paridade que faz a troca de cérebro caber numa
função só, _classe_do_worker() em jarvis/ui/janela_principal.py, que
lê PROVEDOR_IA do .env (ver jarvis/nucleo/config.py):

  gemini/          GeminiLiveWorker      PROVEDOR_IA=gemini (padrão)
  openai_realtime/ OpenAIRealtimeWorker  PROVEDOR_IA=openai
  voz_local/       VozLocalWorker        PROVEDOR_IA=local

Esta pasta é ORGANIZAÇÃO, não uma camada nova: não há classe base
comum, nem despacho aqui dentro, e este __init__ não importa nenhum
worker de propósito — importar os três de uma vez arrastaria as
dependências dos três (google-genai, websockets, paho) para quem só
vai usar um. Cada cliente importa o subpacote que precisa.
"""
