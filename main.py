### NOTES
# https://servers-frontend.fivem.net/api/servers/single/{server-shortcut}
#
# NA 1: a6aope
# NA 2: zlvypp
# NA 3: qmv4z4
# EU 1: kx98er
# EU 2: abo683
# SEA : apyap9



import discord
from discord.ext import tasks, commands
import requests
import asyncio
import json
from datetime import datetime, timedelta
import time

# Bot-Setup
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

# Konfiguration
USE_LOCAL_JSON = False  # Umschalten zwischen API und lokaler JSON-Datei
LOCAL_JSON_FILE = "json-formatting.json"  # Lokale JSON-Datei für Testzwecke
API_URLS = {
    "EU1": "https://api.gtacnr.net/cnr/players?serverId=EU1",
    "EU2": "https://api.gtacnr.net/cnr/players?serverId=EU2",
    "NA1": "https://api.gtacnr.net/cnr/players?serverId=US1",
    "NA2": "https://api.gtacnr.net/cnr/players?serverId=US2",
    "SEA": "https://api.gtacnr.net/cnr/players?serverId=SEA",
}
CHECK_INTERVAL = 60
CACHE_UPDATE_INTERVAL = 300
STATUS_CHANNEL_ID = 1320463232128913551  # Ersetze mit der ID des Status-Kanals
GUILD_ID = 1300519755622383689  # Ersetze mit der ID des Ziel-Servers

MENTOR_ROLE_ID = 1320457877508460565
CADET_ROLE_ID = 1320735081379139707
TRAINEE_ROLE_ID = 1320735125809664112
embeds = []

discord_cache = {
    "timestamp": None,
    "members": {},
}

@client.event
async def on_ready():
    print(f"Bot ist online als {client.user}")
    update_game_status.start()

async def fetch_players(region):
    if USE_LOCAL_JSON:
        try:
            with open(LOCAL_JSON_FILE, "r", encoding='utf-8') as file:
                data = json.load(file)
                return data
        except FileNotFoundError:
            print(f"Lokale JSON-Datei {LOCAL_JSON_FILE} nicht gefunden.")
            return []
        except json.JSONDecodeError as e:
            print(f"Fehler beim Lesen der JSON-Datei: {e}")
            return []
    else:
        api_url = API_URLS.get(region)
        if not api_url:
            print(f"Keine API-URL für Region {region} definiert.")
            return []
        try:
            await asyncio.sleep(1)
            response = requests.get(api_url)
            response.raise_for_status()
            data = json.loads(response.text)
            return data
        except requests.RequestException as e:
            print(f"Fehler beim Abrufen der API-Daten von {api_url}: {e}")
            return []

def clean_discord_name(name):
    return name.split(" [SWAT]")[0]


##
## Discord Cache
##

async def update_discord_cache():
    global discord_cache
    now = datetime.utcnow()
    if discord_cache["timestamp"] and now - discord_cache["timestamp"] < timedelta(seconds=CACHE_UPDATE_INTERVAL):
        print("Discord-Cache ist aktuell. Kein Update erforderlich.")
        return

    discord_cache["members"] = {}
    guild = client.get_guild(GUILD_ID)

    if not guild:
        print(f"Bot ist in keinem Server mit der ID {GUILD_ID}.")
        return

    for member in guild.members:
        roles = [role.id for role in member.roles]
        discord_cache["members"][member.display_name] = {
            "id": member.id,
            "roles": roles,
        }

    discord_cache["timestamp"] = now
    print("Discord-Cache wurde aktualisiert:", discord_cache)
    print("\n - \n")

##
## EMBED ERSTELLEN
##

async def create_embed(region, matching_players):
    swat_count = sum(1 for entry in matching_players if entry['type'] == 'unknown' or entry['type'] == 'SWAT' or entry['type'] == 'mentor')
    mentor_count = sum(1 for entry in matching_players if entry['type'] == 'mentor')
    trainee_count = sum(1 for entry in matching_players if entry['type'] == 'trainee' or entry['type'] == 'cadet')
    mentor_embed = ""
    swat_embed = ""
    trainee_embed = ""
    if region == "EU1" or region == "EU2":
        title="\U0001F1EA\U0001F1FA " + str(region)
    elif region == "NA1" or region == "NA2":
        title="\U0001F1FA\U0001F1F8 " + str(region)
    elif region == "SEA":
        title="\U0001F1F8\U0001F1EC " + str(region)
    else:
        title = ""
    embed = discord.Embed(title=title, description="``SWAT Online:  " + str(swat_count) + "``", colour=0x28ef05)
    

    if mentor_count > 0:
        for i in matching_players:
            if i["type"] == "mentor" and i["discord_id"] != None:
                mentor_embed = mentor_embed + f"\n - {i["username"]}" + f" (<@{i['discord_id']}>)"
            elif i["type"] == "mentor":
                mentor_embed = mentor_embed + f"\n - {i["username"]}" + " (?)"
        embed.add_field(name="Mentors Online:", value=mentor_embed, inline=False)

    if swat_count > 0:
        for i in matching_players:
            if i["type"] == "SWAT" and i["discord_id"] != None:
                swat_embed = swat_embed + f"\n - {i["username"]}" + f" (<@{i['discord_id']}>)"
            elif i["type"] == "SWAT" or i["type"] == "unknown":
                swat_embed = swat_embed + f"\n - {i["username"]}" + " (?)"
        embed.add_field(name="SWAT Online:", value=swat_embed, inline=False)

    if trainee_count > 0:
        for i in matching_players:
            if i["type"] == "trainee" and i["discord_id"] != None:
                trainee_embed = trainee_embed + f"\n - T {i["username"]}" + f" (<@{i['discord_id']}>)"
            elif i["type"] == "cadet" and i["discord_id"] != None:
                trainee_embed = trainee_embed + f"\n - C {i["username"]}" + f" (<@{i['discord_id']}>)"
        embed.add_field(name="Cadets / Trainees Online:", value=trainee_embed, inline=False)
    embed.set_footer(text="Refreshes every 60 seconds")
    
    if trainee_count == 0 and mentor_count == 0 and swat_count == 0:
        embed.add_field(name="Nobody is online",value="", inline=False)
    return embed


##
## CHECK PLAYERS
##

@tasks.loop(seconds=CHECK_INTERVAL)
async def update_game_status():
    await update_discord_cache()
    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        print(f"Status-Kanal mit ID {STATUS_CHANNEL_ID} nicht gefunden.")
        print("\n - \n")
        return

    for region in API_URLS.keys():
        print(f"Verarbeite Region: {region}")
        players = await fetch_players(region)
        matching_players = []

        for i in players:
            username = i["Username"]["Username"]
            if username.startswith("[SWAT] "):
                for discord_name, details in discord_cache["members"].items():
                    cleaned_username = username.replace("[SWAT] ","")
                    discord_name = discord_name.replace (" [SWAT]", "")
                    if cleaned_username == discord_name:
                        if MENTOR_ROLE_ID in details["roles"]:
                            matching_players.append({
                                "username": username, 
                                "type": "mentor",
                                "discord_id": details["id"]
                            })
                            break
                        else:
                            matching_players.append({
                                "username": username, 
                                "type": "SWAT",
                                "discord_id": details["id"]
                            })
                            break
                    else:
                        matching_players.append({
                            "username": username, 
                            "type": "SWAT",
                            "discord_id": None
                        })
                        break
            else:
                for discord_name, details in discord_cache["members"].items():
                    if username == discord_name:
                        if CADET_ROLE_ID in details["roles"]:
                            matching_players.append({
                                "username": username, 
                                "type": "cadet",
                                "discord_id": details["id"]
                            })   
                        elif TRAINEE_ROLE_ID in details["roles"]:
                            matching_players.append({
                                "username": username, 
                                "type": "trainee",
                                "discord_id": details["id"]
                            })              
        
        with open("embeds.json", 'r') as file_obj:
            first_char = file_obj.read(1)

        if first_char:
            file_xxxx = open("embeds.json", "r")
            embed_file = json.loads(file_xxxx.read())
            
            print(f"Gefundene Übereinstimmungen für Region {region}: " + str(len(matching_players)))
            embed_pre = await create_embed(region, matching_players)
            for i in embed_file:
                if i["region"] == region:
                    channel = client.get_channel(i["channel_id"])
                    if channel is None:
                        print("Kanal nicht gefunden")
                        return

                    message = await channel.fetch_message(i["message_id"])
                    if message is None:
                        print("nachricht nicht gefunden")
                        return
                    await message.edit(embed=embed_pre)
        else:
            embed_file = ""
            print(f"Gefundene Übereinstimmungen für Region {region}:" + str(len(matching_players)))
            embed_pre = await create_embed(region, matching_players)
            embed_send = await channel.send(embed=embed_pre)
            embeds.append({
                "region": region,
                "channel_id": embed_send.channel.id,
                "message_id": embed_send.id
            })

    if embeds:
        print(embeds)
        f = open("embeds.json", "w")
        f.write(json.dumps(embeds))
        f.close()

# Token laden und Bot starten
with open("token.txt", "r") as file:
    TOKEN = file.read().strip()

client.run(TOKEN)
