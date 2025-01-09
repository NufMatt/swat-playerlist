# config.py
import datetime
from datetime import datetime

# General Bot Settings
USE_LOCAL_JSON = False
LOCAL_JSON_FILE = "json-formatting.json"
CHECK_INTERVAL = 60
CACHE_UPDATE_INTERVAL = 300

# Logging
PClOGGING = True
LOG_FILENAME = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.log')

# Telegram
CHAT_ID = "CHATID"

# Server Data
API_URLS = {
    "EU1": "https://api.gtacnr.net/cnr/players?serverId=EU1",
    "EU2": "https://api.gtacnr.net/cnr/players?serverId=EU2",
    "NA1": "https://api.gtacnr.net/cnr/players?serverId=US1",
    "NA2": "https://api.gtacnr.net/cnr/players?serverId=US2",
    "SEA": "https://api.gtacnr.net/cnr/players?serverId=SEA",
}
API_URLS_FIVEM = {
    "EU1": "https://57.129.49.31:30130/info.json",
    "EU2": "https://57.129.49.31:30131/info.json",
    "NA1": "https://15.204.215.61:30130/info.json",
    "NA2": "https://15.204.215.61:30131/info.json",
    "SEA": "https://51.79.231.52:30130/info.json",
}

# SWAT
'''
STATUS_CHANNEL_ID = 1322097975324971068
GUILD_ID = 958271853158350850
MENTOR_ROLE_ID = 1303048285040410644
CADET_ROLE_ID = 962226985222959145
TRAINEE_ROLE_ID = 1033432392758722682
SWAT_ROLE_ID = 958274314036195359
'''

# Testing
STATUS_CHANNEL_ID = 1320463232128913551
GUILD_ID = 1300519755622383689
MENTOR_ROLE_ID = 1303048285040410644
CADET_ROLE_ID = 962226985222959145
TRAINEE_ROLE_ID = 1033432392758722682
SWAT_ROLE_ID = 958274314036195359

# Ranking
RANK_HIERARCHY = [
    "Mentor", "Chief", "Deputy Chief", "Commander",
    "Captain", "Lieutenant", "Seargent", "Corporal",
    "Officer", "Cadet", "Trainee", None
]
ROLE_TO_RANK = {
    1303048285040410644: "Mentor",
    958272560905195521: "Chief",
    958272662080225290: "Deputy Chief",
    958272697291407360: "Commander",
    958272723975553085: "Captain",
    958272744800260126: "Lieutenant",
    958272773904543775: "Seargent",
    966118860128411681: "Corporal",
    958272804011245618: "Officer",
    962226985222959145: "Cadet",
    1033432392758722682: "Trainee",
}

# Files
EMBEDS_FILE = "embeds-testing.json"

# Token Files
TOKEN_FILE = "token-test.txt"
