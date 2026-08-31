# Pacote mínimo, não é um pacote de tools (sem
# obter_function_declarations()/despachar(), não entra em
# PACOTES_REGISTRADOS) — só lê config.json da raiz do projeto. Ver
# config/carregador.py e INTEGRATION.md, seção "Interrupção de fala
# (config.json)".
from config.carregador import interrupcao_ativa
