"""
Terceiro cérebro de voz do ALFRED: o servidor local (alfred-server),
rodando em Docker nesta máquina e conversando por MQTT.

Alternativa ao Gemini Live (jarvis/cerebro/gemini/cliente_live.py) e à
Realtime API da OpenAI (jarvis/cerebro/openai_realtime/), escolhida pela
variável PROVEDOR_IA do .env — ver jarvis/nucleo/config.py e
jarvis/ui/janela_principal.py. Os três workers expõem a MESMA API
pública (sinais, construtor e métodos), então trocar de cérebro não
mexe na interface.

O turno aqui tem três partes: o servidor transcreve o áudio (etapa 1),
o texto passa por jarvis/roteamento_hierarquico para decidir se era
ferramenta ou conversa, e só no segundo caso o servidor é chamado de
novo para falar a resposta (etapa 2). Ferramentas portanto FUNCIONAM
neste modo — quem as escolhe e executa é o roteamento, não o servidor.

O que este modo não tem: perfis, prompt de sistema, gate da
palavra-chave e retomada de sessão. Ver o cabeçalho de
cliente_local.py para a lista completa e o porquê de cada uma.

Não confundir com jarvis/pacotes/rede_jarvis/, que também usa MQTT mas
para outra coisa (comandos entre máquinas) e contra outro broker.
"""

from jarvis.cerebro.voz_local.cliente_local import VozLocalWorker

__all__ = ["VozLocalWorker"]
