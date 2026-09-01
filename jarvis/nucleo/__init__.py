# Núcleo da aplicação: o que todo o resto depende e que não pertence
# a nenhuma integração específica.
#
#   config.py        -> credenciais e opções do Gemini, lidas do .env
#   preferencias.py  -> preferências locais lidas do config.json
#   sinalizador.py   -> ponte de Signals entre threads de fundo e a GUI
