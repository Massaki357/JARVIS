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
import jarvis.pacotes.abrir_app_local.config as abrir_app_local_config
import jarvis.pacotes.admin_terminal.config as admin_terminal_config
import jarvis.pacotes.ativacao_voz.config as ativacao_voz_config
import jarvis.pacotes.casa_inteligente.config as casa_inteligente_config
import jarvis.pacotes.cerebro_reserva.config as cerebro_reserva_config
import jarvis.pacotes.criar_arquivo.config as criar_arquivo_config
import jarvis.pacotes.delegacao_ia.config as delegacao_ia_config
import jarvis.pacotes.identificacao_planta.config as identificacao_planta_config
import jarvis.pacotes.memoria_obsidian.config as memoria_obsidian_config
import jarvis.pacotes.identificacao_visual.config as identificacao_visual_config
import jarvis.pacotes.navegador_jarvis.config as navegador_jarvis_config
import jarvis.pacotes.rede_jarvis.config as rede_jarvis_config

# Estes dois não são pacotes de tools (jarvis/pacotes/) — são módulos
# centrais (jarvis/nucleo/) e de infraestrutura compartilhada
# (jarvis/servicos/) que também leem variáveis do .env, e por isso
# também ganham config_schema(). Lacuna fechada: até aqui a tela de
# configurações cobria só pacotes de tools — GEMINI_API_KEY e as
# variáveis de email nunca tinham aparecido nela.
import jarvis.nucleo.config as nucleo_config
import jarvis.servicos.email.remetente as email_remetente_config
import jarvis.servicos.email.leitor as email_leitor_config

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
    ("Memória (vault do Obsidian)", memoria_obsidian_config),
    (
        "Cérebro Reserva (assume quando o Gemini falha)",
        cerebro_reserva_config,
    ),
    ("Navegador (Playwright)", navegador_jarvis_config),
    ("Abrir Aplicativo Local (pastas extras)", abrir_app_local_config),
    ("Criar Arquivo (pastas permitidas)", criar_arquivo_config),
    ("Gemini / Núcleo do ALFRED", nucleo_config),
    ("Email — Envio (SMTP)", email_remetente_config),
    ("Email — Leitura (IMAP)", email_leitor_config),
]
