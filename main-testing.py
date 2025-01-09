import discord
from discord.ext import tasks, commands
import requests, json, datetime, re, pytz, logging, os, sys, aiohttp, asyncio
from datetime import datetime, timedelta
from config import (
    USE_LOCAL_JSON, LOCAL_JSON_FILE, CHECK_INTERVAL, CACHE_UPDATE_INTERVAL,
    PClOGGING, LOG_FILENAME, CHAT_ID, API_URLS, API_URLS_FIVEM, STATUS_CHANNEL_ID, 
    GUILD_ID, MENTOR_ROLE_ID, CADET_ROLE_ID, TRAINEE_ROLE_ID, SWAT_ROLE_ID,
    RANK_HIERARCHY, ROLE_TO_RANK, EMBEDS_FILE, TOKEN_FILE
)

requests.packages.urllib3.disable_warnings()

# Bot setup
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

# Logging setup
if PClOGGING:
    log_filepath = LOG_FILENAME
else:
    log_filepath = os.path.join("/opt/swat-server-list/", LOG_FILENAME)
logging.basicConfig(
    filename=log_filepath,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# Global variables
embeds = []
discord_cache = {"timestamp": None, "members": {}}

def send_telegram(message_temp):
    with open("tgtoken.txt", "r") as file:
        TGTOKEN = file.read().strip()
    url = f"https://api.telegram.org/bot{TGTOKEN}/sendMessage?chat_id={CHAT_ID}&text={message_temp}"
    requests.get(url).json()

def log(log_type, content):
    ts = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    print(f"[{ts}] {content}")
    if log_type == "warning": logging.warning(content)
    elif log_type == "error":
        logging.error(content)
        send_telegram(f"ERROR: [{ts}] {content}")
    elif log_type == "critical":
        logging.critical(content)
        send_telegram(f"CRITICAL: [{ts}] {content}")
    else:
        logging.info(content)

def fix_encoding_latin1_to_utf8(text: str) -> str:
    return text.encode('latin-1', errors='replace').decode('utf-8', errors='replace')

@client.event
async def on_ready():
    log("info", f"Bot ist online als {client.user}")
    update_game_status.start()

@client.event
async def on_error(event, *args, **kwargs):
    log("critical", f'Fehler im Event {event}: {args} {kwargs}')
    sys.exit(1)

async def fetch_players(region):
    if USE_LOCAL_JSON:
        try:
            with open(LOCAL_JSON_FILE, "r", encoding='utf-8') as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log("error", f"Fehler beim Lesen der JSON-Datei: {e}")
            return []
    url = API_URLS.get(region)
    if not url:
        log("error", f"Keine API-URL für Region {region} definiert.")
        return []
    try:
        async with aiohttp.ClientSession() as session:
            await asyncio.sleep(1)
            async with session.get(url) as resp:
                resp.raise_for_status()
                resp.encoding = 'latin-1'
                data = json.loads(fix_encoding_latin1_to_utf8(await resp.text()))
                return data
    except aiohttp.ClientError as e:
        log("error", f"Fehler beim Abrufen der API-Daten: {e}")
        return None

async def getqueuedata():
    try:
        r = requests.get("https://api.gtacnr.net/cnr/servers")
        r.raise_for_status()
        data = json.loads(r.text)
        queue_info = {entry["Id"]: entry for entry in data}
        if "US1" in queue_info: queue_info["NA1"] = queue_info.pop("US1")
        if "US2" in queue_info: queue_info["NA2"] = queue_info.pop("US2")
        return queue_info
    except requests.RequestException as e:
        log("error", f"Fehler beim Abrufen der Queue-Daten: {e}")
        return None

async def get_fivem_data():
    fivem_data = {}
    async with aiohttp.ClientSession() as session:
        for region, url in API_URLS_FIVEM.items():
            try:
                async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=3)) as response:
                    response.raise_for_status()
                    fivem_data[region] = json.loads(await response.text())
            except Exception as e:
                log("warning", f"Fehler beim Abrufen der Fivem Daten {region}: {e}")
                fivem_data[region] = None
    return fivem_data

async def update_discord_cache():
    now = datetime.now()
    if discord_cache["timestamp"] and now - discord_cache["timestamp"] < timedelta(seconds=CACHE_UPDATE_INTERVAL):
        log("info", "Discord-Cache ist aktuell. Kein Update erforderlich.")
        return
    guild = client.get_guild(GUILD_ID)
    if not guild:
        log("error", f"Bot ist in keinem Server mit der ID {GUILD_ID}.")
        return
    dc_members = {m.display_name: {"id": m.id, "roles": [r.id for r in m.roles]} for m in guild.members}
    discord_cache.update({"timestamp": now, "members": dc_members})
    log("info", "Discord-Cache wurde aktualisiert!")

def time_convert(time_string):
    # Next Restart Time converter for FiveM
    m = re.match(r'^(.+) (\d{2}):(\d{2})$', time_string)
    if not m: return "*Restarting now*"
    d, hh, mm = m.groups()
    hh, mm = int(hh), int(mm)
    days = ['Saturday','Friday','Thursday','Wednesday','Tuesday','Monday','Sunday']
    total_hours = (days.index(d)*24*60 + (24-hh-1)*60 + (60-mm))//60
    if not total_hours: return "*Restarting now*"
    h, r = divmod(total_hours, 60)
    hs = f"{h} hour{'s'*(h!=1)}" if h else ""
    rs = f"{r} minute{'s'*(r!=1)}" if r else ""
    return f"*Next restart in ~{hs+' and '+rs if hs and rs else hs or rs}*"

def get_rank_from_roles(roles):
    for r_id, rank in ROLE_TO_RANK.items():
        if r_id in roles: return rank
    return None

async def create_embed(region, matching_players, queue_data, fivem_data):
    offline = False
    embed_color = 0x28ef05  # default green

    if queue_data and region in queue_data:
        try:
            last_heartbeat = datetime.fromisoformat(
                queue_data[region]["LastHeartbeatDateTime"].replace("Z", "+00:00")
            )
            if datetime.now(pytz.UTC) - last_heartbeat > timedelta(minutes=10):
                offline = True
                embed_color = 0xf40006  # red
        except:
            pass
    else:
        offline = True
        embed_color = 0xf40006  # red

    flags = {"EU": "🇪🇺 ", "NA": "🇺🇸 ", "SEA": "🇸🇬 "}
    region_name = region[:-1] if region[-1].isdigit() else region
    title = f"{flags.get(region_name, '')}{region}"
    # Emojis from server (if not found, default to circle)
    def safe_emoji(eid, default="⚫"):
        e = client.get_emoji(eid)
        return str(e if e else default)

    embed = discord.Embed(title=title, colour=embed_color)
    offline = False

    # Check if server offline / no data
    if matching_players is not None and offline is not True:
        swat_count = sum(p["type"] in ("unknown", "SWAT", "mentor") for p in matching_players)
        mentor_count = sum(p["type"] == "mentor" for p in matching_players)
        trainee_count = sum(p["type"] in ("trainee", "cadet") for p in matching_players)
        
        # Try to read FiveM "Time" for next restart
        try:
            restart_timer = time_convert(fivem_data[region]["vars"]["Time"])
        except:
            restart_timer = "*No restart data available!*"

        # Mentor
        if mentor_count:
            val = ""
            for mp in matching_players:
                if mp["type"] == "mentor":
                    val += f"\n - {mp['username']} (<@{mp['discord_id']}>)" if mp['discord_id'] else f"\n - {mp['username']} (❔)"
            embed.add_field(name=f"{safe_emoji(1305249069463113818)}Mentors Online:", value=val, inline=False)

        # SWAT
        if swat_count - mentor_count > 0:
            val = ""
            for mp in matching_players:
                if mp["type"] in ("SWAT", "unknown"):
                    val += f"\n - {mp['username']} (<@{mp['discord_id']}>)" if mp['discord_id'] else f"\n - {mp['username']} (❔)"
            embed.add_field(name="SWAT Online:", value=val, inline=False)

        # Trainees / Cadets
        if trainee_count:
            val = ""
            for mp in matching_players:
                if mp["type"] == "trainee":
                    val += f"\n{safe_emoji(1305496951642390579)} {mp['username']} (<@{mp['discord_id']}>)"
                elif mp["type"] == "cadet":
                    val += f"\n{safe_emoji(1305496985582698607)} {mp['username']} (<@{mp['discord_id']}>)"
            embed.add_field(name="Cadets / Trainees Online:", value=val, inline=False)

        if all(p["type"] not in ("SWAT","mentor","trainee","cadet","unknown") for p in matching_players):
            embed.add_field(name="\n*Nobody is online*\n", value="", inline=False)

        # Stats
        if queue_data and region in queue_data:
            p = queue_data[region]
            embed.add_field(name=f"{safe_emoji(1196404423874854992)}SWAT:", value=f"``` {swat_count} ```", inline=True)
            embed.add_field(name="🎮Players:", value=f"```{p['Players']}/{p['MaxPlayers']}```", inline=True)
            embed.add_field(name="⌛Queue:", value=f"```{p['QueuedPlayers']}```", inline=True)
            embed.add_field(name="", value=restart_timer, inline=False)
        else:
            embed.add_field(name=f"{safe_emoji(1196404423874854992)}SWAT:", value=f"```{swat_count}```", inline=True)
            embed.add_field(name="🎮Players:", value="```no data```", inline=True)
            embed.add_field(name="⌛Queue:", value="```no data```", inline=True)
    else:
        embed.add_field(name="Server or API down?", value="No Data for this server!", inline=False)
        embed.add_field(name="🎮Players:", value="```no data```", inline=True)
        embed.add_field(name="⌛Queue:", value="```no data```", inline=True)

    embed.set_footer(text="Refreshes every 60 second")
    embed.timestamp = datetime.now()
    return embed

@tasks.loop(seconds=CHECK_INTERVAL)
async def update_game_status():
    await update_discord_cache()
    queue_data = await getqueuedata()
    fivem_data = await get_fivem_data()
    embed_file_name = EMBEDS_FILE
    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel: return log("error", f"Status-Kanal {STATUS_CHANNEL_ID} nicht gefunden.")

    for region in API_URLS.keys():
        log("info", f"Verarbeite Region: {region}")
        players = await fetch_players(region)
        matching_players = None if players is None else []
        if players:
            for pl in players:
                username = pl["Username"]["Username"]
                if any(mp["username"] == username for mp in matching_players): 
                    continue  # skip duplicates
                # Check for [SWAT]
                if username.startswith("[SWAT] "):
                    cleaned_name = re.sub(r'^\[SWAT\]\s*', '', username, flags=re.IGNORECASE)
                    discord_found = False
                    for dn, dt in discord_cache["members"].items():
                        compare_dn = re.sub(r'^\[SWAT\]\s*', '', dn, flags=re.IGNORECASE)
                        if cleaned_name.lower() == compare_dn.lower():
                            discord_found = True
                            mtype = "mentor" if MENTOR_ROLE_ID in dt["roles"] else "SWAT"
                            matching_players.append({"username": username, "type": mtype, "discord_id": dt["id"], "rank": get_rank_from_roles(dt["roles"])})
                            break
                    if not discord_found:
                        matching_players.append({"username": username, "type": "SWAT", "discord_id": None, "rank": None})
                else:
                    # Check for cadet / trainee / swat from roles if name matches
                    for dn, dt in discord_cache["members"].items():
                        tmp_dn = re.sub(r'\s*\[(CADET|TRAINEE|SWAT)\]$', '', dn, flags=re.IGNORECASE)
                        if username.lower() == tmp_dn.lower():
                            if CADET_ROLE_ID in dt["roles"]:
                                matching_players.append({"username": username, "type": "cadet", "discord_id": dt["id"], "rank": get_rank_from_roles(dt["roles"])})
                            elif TRAINEE_ROLE_ID in dt["roles"]:
                                matching_players.append({"username": username, "type": "trainee", "discord_id": dt["id"], "rank": get_rank_from_roles(dt["roles"])})
                            elif SWAT_ROLE_ID in dt["roles"]:
                                matching_players.append({"username": username, "type": "SWAT", "discord_id": dt["id"], "rank": get_rank_from_roles(dt["roles"])})
                            break
        if matching_players is not None:
            matching_players.sort(key=lambda x: RANK_HIERARCHY.index(x["rank"]) if x["rank"] in RANK_HIERARCHY else len(RANK_HIERARCHY))

        # Create new embed
        embed_pre = await create_embed(region, matching_players, queue_data, fivem_data)
        # Update existing or create new
        if os.path.exists(embed_file_name) and os.path.getsize(embed_file_name) > 0:
            with open(embed_file_name, "r") as f:
                stored_embeds = json.load(f)
            for em in stored_embeds:
                if em["region"] == region:
                    msg = await client.get_channel(em["channel_id"]).fetch_message(em["message_id"])
                    await msg.edit(embed=embed_pre)
                    break
            else:
                msg_send = await channel.send(embed=embed_pre)
                stored_embeds.append({"region": region, "channel_id": msg_send.channel.id, "message_id": msg_send.id})
            with open(embed_file_name, "w") as f:
                json.dump(stored_embeds, f)
        else:
            msg_send = await channel.send(embed=embed_pre)
            new_data = [{"region": region, "channel_id": msg_send.channel.id, "message_id": msg_send.id}]
            with open(embed_file_name, "w") as f:
                json.dump(new_data, f)

# --- Bot Token Loader ---
file_name = TOKEN_FILE
with open(file_name, "r") as file:
    TOKEN = file.read().strip()

try:
    client.run(TOKEN)
except Exception as e:
    log("critical", f"Bot Fehler: {e}")
    sys.exit(1)