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
import datetime
from datetime import datetime, timedelta
import time

# Bot-Setup
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

# Konfiguration
USE_LOCAL_JSON = False  # Umschalten zwischen API und lokaler JSON-Datei
LOCAL_JSON_FILE = "json-formatting.json"  # Lokale JSON-Datei für Testzwecke
API_URLS_BROKEN = {
    "EU1": "https://api.gtacnr.net/cnr/players?serverId=EA1",
    "EU2": "https://api.gtacnr.net/cnr/players?serverId=EA2",
    "NA1": "https://api.gtacnr.net/cnr/players?serverId=UA1",
    "NA2": "https://api.gtacnr.net/cnr/players?serverId=UA2",
    "SEA": "https://api.gtacnr.net/cnr/players?serverId=SAA",
}

API_URLS = {
    "EU1": "https://api.gtacnr.net/cnr/players?serverId=EU1",
    "EU2": "https://api.gtacnr.net/cnr/players?serverId=EU2",
    "NA1": "https://api.gtacnr.net/cnr/players?serverId=US1",
    "NA2": "https://api.gtacnr.net/cnr/players?serverId=US2",
    "SEA": "https://api.gtacnr.net/cnr/players?serverId=SEA",
}

CHECK_INTERVAL = 60
CACHE_UPDATE_INTERVAL = 300
STATUS_CHANNEL_ID = 1322097975324971068  # Ersetze mit der ID des Status-Kanals
GUILD_ID = 958271853158350850  # Ersetze mit der ID des Ziel-Servers
MENTOR_ROLE_ID = 1303048285040410644
CADET_ROLE_ID = 962226985222959145
TRAINEE_ROLE_ID = 1033432392758722682

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
            response.encoding = 'utf-8'
            data = json.loads(response.text)
            return data
        except requests.RequestException as e:
            print(f"Fehler beim Abrufen der API-Daten von {api_url}: {e}")
            return None # return None überall da, wo fetch_players ausgelesen wird

def clean_discord_name(name):
    return name.split(" [SWAT]")[0]

async def getqueuedata():
    queueerror = False
    try:
        response = requests.get("https://api.gtacnr.net/cnr/servers")
        response.raise_for_status()
        response.encoding = 'utf-8'
        data = json.loads(response.text)

        queue_info = {entry["Id"]: entry for entry in data}
        queue_info["NA1"] = queue_info.pop("US1")
        queue_info["NA2"] = queue_info.pop("US2")
        queueerror = False
        return queue_info
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen der Queue-Daten: {e}")
        return None

##
## Discord Cache
##

async def update_discord_cache():
    global discord_cache
    now = datetime.now()
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
    print("Discord-Cache wurde aktualisiert!")
    print("\n - \n")

##
## EMBED ERSTELLEN
##

async def create_embed(region, matching_players, queue_data):
    if region == "EU1" or region == "EU2":
        title="\U0001F1EA\U0001F1FA " + str(region)
    elif region == "NA1" or region == "NA2":
        title="\U0001F1FA\U0001F1F8 " + str(region)
    elif region == "SEA":
        title="\U0001F1F8\U0001F1EC " + str(region)
    else:
        title = ""
    
    emoji_swat_logo = client.get_emoji(1196404423874854992)  # Emoji-ID hier einfügen
    if not emoji_swat_logo:
        emoji_swat_logo = "⚫"
    else:
        emoji_swat_logo = str(emoji_swat_logo)
    
    emoji_swat_mentor = client.get_emoji(1305249069463113818)  # Emoji-ID hier einfügen
    if not emoji_swat_mentor:
        emoji_swat_mentor = "⚫"
    else:
        emoji_swat_mentor = str(emoji_swat_mentor)

    emoji_swat_cadet = client.get_emoji(1305496985582698607)  # Emoji-ID hier einfügen
    if not emoji_swat_cadet:
        emoji_swat_cadet = "⚫"
    else:
        emoji_swat_cadet = str(emoji_swat_cadet)
        
    emoji_swat_trainee = client.get_emoji(1305496951642390579)  # Emoji-ID hier einfügen
    if not emoji_swat_trainee:
        emoji_swat_trainee = "⚫"
    else:
        emoji_swat_trainee = str(emoji_swat_trainee)

    if not (matching_players == None):
        embed = discord.Embed(title=title, description="", colour=0x28ef05)
        
        swat_count = sum(1 for entry in matching_players if entry['type'] == 'unknown' or entry['type'] == 'SWAT' or entry['type'] == 'mentor')
        swat_count_no_mentor = sum(1 for entry in matching_players if entry['type'] == 'unknown' or entry['type'] == 'SWAT')
        mentor_count = sum(1 for entry in matching_players if entry['type'] == 'mentor')
        trainee_count = sum(1 for entry in matching_players if entry['type'] == 'trainee' or entry['type'] == 'cadet')
        mentor_embed = ""
        swat_embed = ""
        trainee_embed = ""

        if mentor_count > 0:
            for i in matching_players:
                if i["type"] == "mentor" and i["discord_id"] != None:
                    mentor_embed = mentor_embed + "\n - " + i["username"] + "   (<@" + str(i['discord_id']) + ">)"
                elif i["type"] == "mentor":
                    mentor_embed = mentor_embed + "\n - " + i["username"] + " (❔)"
            embed.add_field(name=emoji_swat_mentor + "Mentors Online:", value=mentor_embed, inline=False)

        if swat_count_no_mentor > 0:
            for i in matching_players:
                if i["type"] == "SWAT" and i["discord_id"] != None:
                    swat_embed = swat_embed + "\n - " + i["username"] + "   (<@" + str(i['discord_id']) + ">)"
                elif i["type"] == "SWAT" or i["type"] == "unknown":
                    swat_embed = swat_embed + "\n - " + i["username"] + " (❔)"
            embed.add_field(name="SWAT Online:", value=swat_embed, inline=False)

        if trainee_count > 0:
            for i in matching_players:
                if i["type"] == "trainee" and i["discord_id"] != None:
                    trainee_embed = trainee_embed + "\n" + emoji_swat_trainee + " " + i["username"] + "   (<@" + str(i['discord_id']) + ">)"
                elif i["type"] == "cadet" and i["discord_id"] != None:
                    trainee_embed = trainee_embed + "\n" + emoji_swat_cadet + " " + i["username"] + "   (<@" + str(i['discord_id']) + ">)"
            embed.add_field(name="Cadets / Trainees Online:", value=trainee_embed, inline=False)

        if trainee_count == 0 and mentor_count == 0 and swat_count == 0:
            embed.add_field(name="\n*Nobody is online*\n",value="", inline=False)

        if not queue_data == None:
            embed.add_field(name=emoji_swat_logo + "SWAT:", value="``` " + str(swat_count) + "```", inline=True)
            embed.add_field(name="🎮Players:", value="```" + str(queue_data[region]["Players"]) + "/" + str(queue_data[region]["MaxPlayers"]) + "```", inline=True)
            embed.add_field(name="⌛Queue", value="```" + str(queue_data[region]["QueuedPlayers"]) + "```", inline=True)
        else:
            embed.add_field(name=emoji_swat_logo + "SWAT:", value="``` " + str(swat_count) + "```", inline=True)
            embed.add_field(name="🎮Players:", value="```no data```", inline=True)
            embed.add_field(name="⌛Queue", value="```no data```", inline=True)
        embed.set_footer(text="Refreshes every 60 second")
        embed.timestamp = datetime.now()

    else:
        embed = discord.Embed(title=title, description="", colour=0xf40006)
        
        embed.add_field(name="API down?", value="PlayerName API seems down\n Player and Queuedata can still be accurate (if it shows data)", inline=False)

        if not (queue_data == None):
            swat_count = "no data"
            embed.add_field(name=emoji_swat_logo + "SWAT:", value="``` " + str(swat_count) + "```", inline=True)
            embed.add_field(name="🎮Players:", value="```" + str(queue_data[region]["Players"]) + "/" + str(queue_data[region]["MaxPlayers"]) + "```", inline=True)
            embed.add_field(name="⌛Queue", value="```" + str(queue_data[region]["QueuedPlayers"]) + "```", inline=True)
        else:
            embed.add_field(name=emoji_swat_logo + "SWAT:", value="``` " + str(swat_count) + "```", inline=True)
            embed.add_field(name="🎮Players:", value="```no data```", inline=True)
            embed.add_field(name="⌛Queue", value="```no data```", inline=True)
        embed.set_footer(text="Refreshes every 60 second")
        embed.timestamp = datetime.now()
    return embed


##
## CHECK PLAYERS
##

@tasks.loop(seconds=CHECK_INTERVAL)
async def update_game_status():
    await update_discord_cache()
    
    queue_data = await getqueuedata()
    
    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        print(f"Status-Kanal mit ID {STATUS_CHANNEL_ID} nicht gefunden.")
        print("\n - \n")
        return

    for region in API_URLS.keys():  # für jeden Server
        print(f"Verarbeite Region: {region}")
        players = await fetch_players(region)

        if not(players == None):
            matching_players = []
            for i in players:  # für jeden Spieler auf dem Server
                username = i["Username"]["Username"]
                if any(playercheck["username"] == username for playercheck in matching_players):
                    continue  # Überspringe, wenn der Nutzername bereits in matching_players ist

                if username.startswith("[SWAT] "):  # Spieler hat SWAT im Namen
                    cleaned_username = username.replace("[SWAT] ", "")
                    discord_found = False

                    for discord_name, details in discord_cache["members"].items():
                        discord_name = discord_name.replace(" [SWAT]", "")
                        if str(cleaned_username) == str(discord_name):  # Nutzername auf Discord gefunden
                            discord_found = True
                            user_type = "mentor" if MENTOR_ROLE_ID in details["roles"] else "SWAT"
                            matching_players.append({
                                "username": username,
                                "type": user_type,
                                "discord_id": details["id"]
                            })
                            print(f"Spieler ist auf Discord: {username} ({user_type})")
                            break  # Discord-Match gefunden, weitere Prüfung abbrechen

                    if not discord_found:  # Kein Match auf Discord gefunden
                        matching_players.append({
                            "username": username,
                            "type": "SWAT",
                            "discord_id": None
                        })
                        print(f"Spieler nicht auf Discord: {username}")

                else:  # Spieler ohne SWAT-Tag
                    for discord_name, details in discord_cache["members"].items():
                        if discord_name.endswith(" [CADET]"):
                            discord_name = discord_name.replace(" [CADET]", "")
                        elif discord_name.endswith(" [TRAINEE]"):
                            discord_name = discord_name.replace(" [TRAINEE]", "")
                            
                        if username == discord_name:
                            print(username, discord_name)
                            if CADET_ROLE_ID in details["roles"]:
                                matching_players.append({
                                    "username": username,
                                    "type": "cadet",
                                    "discord_id": details["id"]
                                })
                                print(f"Spieler ist ein Cadet: {username}")
                                break
                            elif TRAINEE_ROLE_ID in details["roles"]:
                                matching_players.append({
                                    "username": username,
                                    "type": "trainee",
                                    "discord_id": details["id"]
                                })
                                print(f"Spieler ist ein Trainee: {username}")
                                break
        else:
            matching_players = None

        with open("embeds.json", 'r') as file_obj:
            first_char = file_obj.read(1)
            
        if matching_players == None:
            player_count = 0
        else:
            player_count = len(matching_players)

        if first_char:
            file_xxxx = open("embeds.json", "r")
            embed_file = json.loads(file_xxxx.read())

            
            print(f"Gefundene Übereinstimmungen für Region {region}: " + str(player_count))
            embed_pre = await create_embed(region, matching_players, queue_data)
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
                    await asyncio.sleep(1)
                    await message.edit(embed=embed_pre)
        else:
            embed_file = ""
            print(f"Gefundene Übereinstimmungen für Region {region}:" + str(player_count))
            embed_pre = await create_embed(region, matching_players, queue_data)
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
