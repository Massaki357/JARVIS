import jarvis.pacotes.abrir_aplicativo.config as abrir_aplicativo_config
import jarvis.pacotes.admin_terminal.config as admin_terminal_config
import jarvis.pacotes.agente_ferramentas.config as agente_ferramentas_config
import jarvis.pacotes.ativacao_voz.config as ativacao_voz_config
import jarvis.pacotes.casa_inteligente.config as casa_inteligente_config
import jarvis.pacotes.criar_arquivo.config as criar_arquivo_config
import jarvis.pacotes.delegacao_ia.config as delegacao_ia_config
import jarvis.pacotes.identificacao_planta.config as identificacao_planta_config
import jarvis.pacotes.memoria_obsidian.config as memoria_obsidian_config
import jarvis.pacotes.descricao_visual.config as descricao_visual_config
import jarvis.pacotes.identificacao_visual.config as identificacao_visual_config
import jarvis.pacotes.consulta_acoes.config as consulta_acoes_config
import jarvis.pacotes.rede_jarvis.config as rede_jarvis_config

import jarvis.roteamento_hierarquico.config as roteamento_hierarquico_config

import jarvis.nucleo.config as nucleo_config

import jarvis.cerebro.voz_local.config as voz_local_config
import jarvis.servicos.email.remetente as email_remetente_config
import jarvis.servicos.email.leitor as email_leitor_config

PACOTES_COM_CONFIG = [
    ("Rede Jarvis (comandos remotos via MQTT)", rede_jarvis_config),
    ("Casa Inteligente (Tuya)", casa_inteligente_config),
    ("Delegação de IA (Groq / Cerebras / OpenAI)", delegacao_ia_config),
    (
        "Sub-agente de Ferramentas (Groq)",
        agente_ferramentas_config,
    ),
    ("Comandos Administrativos", admin_terminal_config),
    ("Identificação de Plantas (Pl@ntNet)", identificacao_planta_config),
    ("Segunda Opinião Visual (Mistral)", identificacao_visual_config),
    ("Descrição de Tela e Câmera (Mistral)", descricao_visual_config),
    ("Ativação por Voz (Vosk, 100% local)", ativacao_voz_config),
    ("Memória (vault do Obsidian)", memoria_obsidian_config),
    ("Cotação de Ações (Twelve Data)", consulta_acoes_config),
    ("Abrir Aplicativo (pastas extras)", abrir_aplicativo_config),
    ("Criar Arquivo (pastas permitidas)", criar_arquivo_config),
    (
        "Roteamento Hierárquico de Ferramentas (Groq)",
        roteamento_hierarquico_config,
    ),
    ("Gemini / Núcleo do ALFRED", nucleo_config),
    ("Servidor de Voz Local (alfred-server, MQTT)", voz_local_config),
    ("Email — Envio (SMTP)", email_remetente_config),
    ("Email — Leitura (IMAP)", email_leitor_config),
]
