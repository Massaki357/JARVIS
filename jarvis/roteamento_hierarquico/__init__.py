# Motor de roteamento hierárquico de ferramentas em duas etapas,
# sobre a API de Chat Completions da Groq (sem estado). Ver
# roteador.py para a lógica e config.py/catalogo.py para o porquê de
# cada decisão de design — resumo completo no plano da tarefa.
#
# Módulo standalone: não é um "pacote de tool" (não expõe
# obter_function_declarations()/despachar() pro contrato padrão de
# jarvis/nucleo/registro_pacotes.py) e não está plugado a nenhum dos
# dois cérebros de voz atuais (Gemini Live / OpenAI Realtime) ainda.
# É infraestrutura de raciocínio pronta pra ser importada por um
# pipeline futuro (ex.: o do servidor dedicado STT/TTS via MQTT)
# depois que esse já tiver o texto transcrito do usuário.
from .roteador import processar_turno

__all__ = ["processar_turno"]
