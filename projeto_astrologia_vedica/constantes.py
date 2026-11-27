"""
constantes.py
=============
Tabelas fixas da astrologia védica (Jyotish): signos, regentes e Nakshatras.

Este arquivo NÃO faz cálculos astronômicos. Ele só guarda nomes e regras
tradicionais que o arquivo astrologia.py usa para "traduzir" as longitudes
calculadas pelo Swiss Ephemeris em signo, nakshatra, pada etc.
"""

APP_VERSAO = "1.0.0"

# ---------------------------------------------------------------------------
# IMPORTANTE: o serviço gratuito de busca de cidades (Nominatim/OpenStreetMap)
# exige que cada aplicativo se identifique. Troque o texto abaixo pelo nome do
# seu trabalho e pelo seu e-mail antes de usar de verdade.
# ---------------------------------------------------------------------------
USER_AGENT = "astrologia-vedica-trabalho-universitario (contato: seu_email@exemplo.com)"

# ---------------------------------------------------------------------------
# Os 12 signos (rashis), na ordem do zodíaco, começando em 0° (Mesha/Áries).
# Cada item: (nome em sânscrito, nome em português, regente)
# ---------------------------------------------------------------------------
SIGNOS = [
    ("Mesha", "Áries", "Mangala"),
    ("Vrishabha", "Touro", "Shukra"),
    ("Mithuna", "Gêmeos", "Budha"),
    ("Karka", "Câncer", "Chandra"),
    ("Simha", "Leão", "Surya"),
    ("Kanya", "Virgem", "Budha"),
    ("Tula", "Libra", "Shukra"),
    ("Vrishchika", "Escorpião", "Mangala"),
    ("Dhanu", "Sagitário", "Guru"),
    ("Makara", "Capricórnio", "Shani"),
    ("Kumbha", "Aquário", "Shani"),
    ("Meena", "Peixes", "Guru"),
]

# ---------------------------------------------------------------------------
# Os 9 Grahas: (nome em sânscrito, nome em português)
# ---------------------------------------------------------------------------
NOMES_GRAHAS = {
    "Surya": "Sol",
    "Chandra": "Lua",
    "Mangala": "Marte",
    "Budha": "Mercúrio",
    "Guru": "Júpiter",
    "Shukra": "Vênus",
    "Shani": "Saturno",
    "Rahu": "Nodo Lunar Norte (médio)",
    "Ketu": "Nodo Lunar Sul (médio)",
}

# ---------------------------------------------------------------------------
# Os 27 Nakshatras (cada um ocupa 13°20' = 360/27 graus).
# ---------------------------------------------------------------------------
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

# Regentes dos Nakshatras segundo o ciclo Vimshottari (9 regentes que se
# repetem 3 vezes ao longo dos 27 nakshatras).
_CICLO_VIMSHOTTARI = [
    "Ketu", "Shukra", "Surya", "Chandra", "Mangala",
    "Rahu", "Guru", "Shani", "Budha",
]
REGENTES_NAKSHATRAS = _CICLO_VIMSHOTTARI * 3

# ---------------------------------------------------------------------------
# Configuração astronômica usada no projeto (apenas para registrar no JSON).
# ---------------------------------------------------------------------------
CONFIGURACAO_TEXTO = {
    "zodiaco": "sideral",
    "ayanamsa": "Lahiri (Chitrapaksha)",
    "nodo_lunar": "médio (Mean Node)",
    "sistema_de_casas": "Whole Sign (signo inteiro)",
}
