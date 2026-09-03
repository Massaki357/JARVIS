"""
Segundo cérebro de voz do ALFRED: a Realtime API da OpenAI.

Alternativa ao Gemini Live (jarvis/gemini/cliente_live.py), escolhida
pela variável PROVEDOR_IA do .env — ver jarvis/nucleo/config.py e
jarvis/ui/janela_principal.py. Os dois workers expõem a MESMA API
pública (sinais, construtor e métodos), então trocar de provedor não
mexe na interface.

Não confundir com jarvis/pacotes/delegacao_ia/, que delega uma
tarefa de TEXTO pontual (incluindo uma segunda opinião via OpenAI)
sem trocar o cérebro da conversa.

Aqui é a sessão de voz principal inteira, só que com outro provedor.
"""

from jarvis.openai_realtime.cliente_realtime import OpenAIRealtimeWorker

__all__ = ["OpenAIRealtimeWorker"]
