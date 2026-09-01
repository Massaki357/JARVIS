# Pacote raiz da aplicação. Tudo que é código do jarvis mora aqui
# dentro, dividido em quatro camadas:
#
#   jarvis/nucleo/    -> configuração, preferências e o sinalizador
#                        compartilhado entre threads
#   jarvis/gemini/    -> o worker da sessão Live (coração do app)
#   jarvis/ui/        -> janelas PySide6
#   jarvis/servicos/  -> infraestrutura reutilizável (visão, email,
#                        memória) usada tanto pelo núcleo quanto
#                        pelos pacotes
#   jarvis/pacotes/   -> um pacote isolado por integração/ferramenta,
#                        seguindo o contrato de docs/INTEGRATION.md
#
# Dados gerados em tempo de execução (memória, caches, logs, fila do
# processo elevado) NUNCA ficam junto do código — vão para dados/, na
# raiz do projeto (ver jarvis/caminhos.py).
