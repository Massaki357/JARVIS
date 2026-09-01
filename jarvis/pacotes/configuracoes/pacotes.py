# Lista explícita dos pacotes que contribuem uma seção à tela de
# configurações, cada um expondo config_schema() no próprio
# config.py (ver README de cada pacote / docs/INTEGRATION.md, seção "Tela
# de configurações", para o formato esperado).
#
# Registro explícito de propósito — mesmo espírito de
# PACOTES_REGISTRADOS em jarvis/gemini/cliente_live.py: adicionar um
# pacote novo com config_schema() é só importar o módulo de config
# dele e acrescentar uma linha aqui, nada mais muda em
# jarvis/pacotes/configuracoes/window.py.
import jarvis.pacotes.admin_terminal.config as admin_terminal_config
import jarvis.pacotes.ativacao_voz.config as ativacao_voz_config
import jarvis.pacotes.casa_inteligente.config as casa_inteligente_config
import jarvis.pacotes.cerebro_reserva.config as cerebro_reserva_config
import jarvis.pacotes.delegacao_ia.config as delegacao_ia_config
import jarvis.pacotes.identificacao_planta.config as identificacao_planta_config
import jarvis.pacotes.identificacao_visual.config as identificacao_visual_config
import jarvis.pacotes.navegador_jarvis.config as navegador_jarvis_config
import jarvis.pacotes.rede_jarvis.config as rede_jarvis_config

# Cada item é (rótulo da seção exibido na tela, módulo de config do
# pacote — precisa ter uma função config_schema()).
PACOTES_COM_CONFIG = [
    ("Rede Jarvis (comandos remotos via MQTT)", rede_jarvis_config),
    ("Casa Inteligente (Tuya)", casa_inteligente_config),
    ("Delegação de IA (Groq / Cerebras / OpenAI)", delegacao_ia_config),
    ("Comandos Administrativos", admin_terminal_config),
    ("Identificação de Plantas (Pl@ntNet)", identificacao_planta_config),
    ("Segunda Opinião Visual (Mistral)", identificacao_visual_config),
    ("Ativação por Voz (Vosk, 100% local)", ativacao_voz_config),
    (
        "Cérebro Reserva (assume quando o Gemini falha)",
        cerebro_reserva_config,
    ),
    ("Navegador (Playwright)", navegador_jarvis_config),
]
