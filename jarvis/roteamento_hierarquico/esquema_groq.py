"""
Conversão das FunctionDeclaration do Gemini para o formato de tools
da etapa 2 do roteamento.

ESTE MÓDULO VIROU UMA FACHADA. A conversão em si mudou de casa: foi
para jarvis/servicos/agentes/ferramentas.py, junto com o resto da
camada de agentes, porque deixou de ser "o conversor da Groq" —
é o mesmo dicionário que o bind_tools() do LangChain entende em
QUALQUER provedor. Manter duas cópias da mesma conversão era
exatamente o tipo de duplicação que a camada existe para acabar.

Os nomes daqui continuam existindo, com a mesma assinatura e o mesmo
comportamento, porque medir_custo.py e o roteador já os importavam —
não havia motivo para quebrar isso. Código novo deve chamar
jarvis.servicos.agentes.ferramentas direto.

O que era verdade e continua sendo, sobre o formato de destino: ele
ANINHA tudo dentro de "function" ({"type": "function", "function":
{"name", ...}}), diferente do formato ACHATADO que
jarvis/cerebro/openai_realtime/esquema.py usa para a Realtime API
({"type", "name", "description", "parameters"} direto). São dois
formatos distintos da mesma OpenAI, e trocá-los não falha de modo
óbvio.
"""

from jarvis.servicos.agentes.ferramentas import (
    converter_declaracao,
    interpretar_argumentos,
    obter_esquemas as obter_schemas_completos,
    obter_todos_os_esquemas as obter_todos_os_schemas,
)

__all__ = [
    "converter_declaracao",
    "interpretar_argumentos",
    "obter_schemas_completos",
    "obter_todos_os_schemas",
]
