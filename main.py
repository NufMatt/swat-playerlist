import discord
from discord.ext import tasks, commands
import requests, json, re, pytz, logging, os, sys, aiohttp, asyncio
from datetime import datetime, timedelta
# Only non‑connection parameters come from config.
from config import (
    USE_LOCAL_JSON, LOCAL_JSON_FILE, CHECK_INTERVAL, CACHE_UPDATE_INTERVAL,
    PClOGGING, LOG_FILENAME, CHAT_ID, STATUS_CHANNEL_ID, 
    GUILD_ID, MENTOR_ROLE_ID, CADET_ROLE_ID, TRAINEE_ROLE_ID, SWAT_ROLE_ID,
    RANK_HIERARCHY, ROLE_TO_RANK, EMBEDS_FILE, TOKEN_FILE
)

# Disable warnings from requests
requests.packages.urllib3.disable_warnings()

# ------------------- Load Servers Config -------------------
SERVERS_CONFIG_FILE = "servers_config.json"
def load_servers_config():
    global SERVERS_CONFIG
    if os.path.exists(SERVERS_CONFIG_FILE):
        try:
            with open(SERVERS_CONFIG_FILE, "r") as f:
                SERVERS_CONFIG = json.load(f)
            logging.info(f"Loaded server config from {SERVERS_CONFIG_FILE}.")
        except Exception as e:
            logging.error(f"Error loading {SERVERS_CONFIG_FILE}: {e}")
            SERVERS_CONFIG = {}
    else:
        SERVERS_CONFIG = {}
        logging.error(f"{SERVERS_CONFIG_FILE} not found. Please create this file with the required server info.")

load_servers_config()

# ------------------- Global Failure Counter -------------------
failure_counts = {}  # e.g. {"NA1": 0, "EU1": 0, ...}

# ------------------- Bot Setup -------------------
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

# ------------------- Logging Setup -------------------
if PClOGGING:
    log_filepath = LOG_FILENAME
else:
    log_filepath = os.path.join("/opt/swat-server-list/", LOG_FILENAME)
logging.basicConfig(
    filename=log_filepath,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# ------------------- Global Variables -------------------
discord_cache = {"timestamp": None, "members": {}}
ERROR_BUFFER_COOLDOWN_SECONDS = 5 * 60  # 5 minutes
error_buffer = []  # collects error/critical messages
error_buffer_start_time = datetime.now()

# ------------------- Testing Override -------------------
# For testing, force specific servers to a given status:
# Set value to True to force "offline", or False to force "online".
TEST_OVERRIDE_STATUS = {
    # "EU1": True,
    # "NA2": True,
}

# ------------------- Desired Online Order -------------------
ORDERED_REGIONS = ["SEA", "NA3", "NA2", "NA1", "EU2", "EU1"]

# ------------------- Players API URL Helper -------------------
def get_players_api_url(region: str) -> str:
    if region.startswith("NA"):
        return f"https://api.gtacnr.net/cnr/players?serverId=US{region[2:]}"
    else:
        return f"https://api.gtacnr.net/cnr/players?serverId={region}"

# ------------------- Normalization Helper -------------------
def normalize_queue_info(data):
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, list):
        queue_info = {entry["Id"]: entry for entry in data}
    elif isinstance(data, dict):
        queue_info = {entry["Id"]: entry for entry in data.get("servers", [])}
    else:
        queue_info = {}
    
    for us, na in [("US1", "NA1"), ("US2", "NA2"), ("US3", "NA3")]:
        if us in queue_info:
            queue_info[na] = queue_info.pop(us)
    return queue_info


# ------------------- Utility Functions -------------------
def send_telegram(message_temp):
    with open("tgtoken.txt", "r") as file:
        TGTOKEN = file.read().strip()
    url = f"https://api.telegram.org/bot{TGTOKEN}/sendMessage?chat_id={CHAT_ID}&text={message_temp}"
    # Uncomment to enable Telegram messaging:
    # requests.get(url).json()

def log(log_type, content):
    global error_buffer, error_buffer_start_time
    ts = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    print(f"[{ts}] {content}")
    if log_type == "warning":
        logging.warning(content)
    elif log_type == "error":
        logging.error(content)
        error_buffer.append(f"[{ts}] ERROR: {content}")
    elif log_type == "critical":
        logging.critical(content)
        error_buffer.append(f"[{ts}] CRITICAL: {content}")
    else:
        logging.info(content)
    now_dt = datetime.now()
    elapsed = (now_dt - error_buffer_start_time).total_seconds()
    if elapsed >= ERROR_BUFFER_COOLDOWN_SECONDS:
        if error_buffer:
            summary_message = ("Fehler/Fehlermeldungen im letzten 5-Minuten-Fenster:\n\n" +
                               "\n".join(error_buffer))
            send_telegram(summary_message)
            error_buffer.clear()
        error_buffer_start_time = now_dt

@client.event
async def on_ready():
    log("info", f"Bot is online as {client.user}")
    update_game_status.start()

@client.event
async def on_error(event, *args, **kwargs):
    log("critical", f"Error in event {event}: {args} {kwargs}")
    sys.exit(1)

# ------------------- API Functions -------------------
async def fetch_players(region):
    if USE_LOCAL_JSON:
        try:
            with open(LOCAL_JSON_FILE, "r", encoding='utf-8') as file:
                data = json.load(file)
                log("info", f"Fetched players from local JSON for region {region}.")
                return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log("error", f"Error reading local JSON file: {e}")
            return []
    url = get_players_api_url(region)
    try:
        await asyncio.sleep(1)
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding='utf-8')
                data = json.loads(text)
                log("info", f"Fetched players for region {region}.")
                return data
    except asyncio.TimeoutError:
        log("error", f"Timeout fetching players for region {region}.")
        return None
    except aiohttp.ClientError as e:
        log("error", f"Error fetching players for region {region}: {e}")
        return None

async def getqueuedata():
    try:
        r = requests.get("https://api.gtacnr.net/cnr/servers", timeout=3)
        r.encoding = 'utf-8'
        r.raise_for_status()
        data = json.loads(r.text)
        queue_info = normalize_queue_info(data)
        log("info", "Fetched queue data.")
        return queue_info
    except requests.Timeout:
        log("error", "Timeout fetching queue data.")
        return None
    except requests.RequestException as e:
        log("error", f"Error fetching queue data: {e}")
        return None

async def get_fivem_data():
    fivem_data = {}
    async with aiohttp.ClientSession() as session:
        for region, config_data in SERVERS_CONFIG.items():
            url = config_data.get("api_url")
            print(url)
            if not url:
                log("error", f"No API URL for region {region}.")
                fivem_data[region] = None
                continue
            try:
                async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    response.raise_for_status()
                    text = await response.text(encoding='utf-8')
                    print(text)
                    fivem_data[region] = json.loads(text)
                    log("info", f"Fetched FiveM data for region {region}.")
                    await asyncio.sleep(1)
            except Exception as e:
                log("warning", f"Error fetching FiveM data for region {region}: {e}")
                fivem_data[region] = None
        print(fivem_data)
        return fivem_data

async def update_discord_cache():
    now = datetime.now()
    if discord_cache["timestamp"] and now - discord_cache["timestamp"] < timedelta(seconds=CACHE_UPDATE_INTERVAL):
        log("info", "Discord cache is current; no update needed.")
        return
    guild = client.get_guild(GUILD_ID)
    if not guild:
        log("error", f"Bot is not in a server with ID {GUILD_ID}.")
        return
    dc_members = {m.display_name: {"id": m.id, "roles": [r.id for r in m.roles]} for m in guild.members}
    discord_cache.update({"timestamp": now, "members": dc_members})
    log("info", "Discord cache updated.")

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
        if r_id in roles:
            return rank
    return None

# ------------------- Embed Creation & Update Functions -------------------
async def create_embed(region, matching_players, queue_data, fivem_data):
    offline = False
    embed_color = 0x28ef05  # green for online
    if matching_players is None or (fivem_data and fivem_data.get(region) is None):
        offline = True
        embed_color = 0xf40006  # red for offline
        log("info", f"Region {region} marked offline (missing players or FiveM data).")
    if queue_data and region in queue_data and not offline:
        try:
            last_heartbeat = datetime.fromisoformat(queue_data[region]["LastHeartbeatDateTime"].replace("Z", "+00:00"))
            if datetime.now(pytz.UTC) - last_heartbeat > timedelta(minutes=10):
                offline = True
                embed_color = 0xf40006
                log("warning", f"Region {region} marked offline (heartbeat outdated).")
        except Exception as e:
            log("error", f"Error processing heartbeat for {region}: {e}")
    else:
        offline = True
        embed_color = 0xf40006

    flags = {"EU": "🇪🇺 ", "NA": "🇺🇸 ", "SEA": "🇸🇬 "}
    region_name = region[:-1] if region[-1].isdigit() else region
    title = f"{flags.get(region_name, '')}{region}"
    embed = discord.Embed(title=title, colour=embed_color)
    
    if offline:
        embed.add_field(name="Server or API down?", value="No Data for this server!", inline=False)
        embed.add_field(name="Players:", value="```no data```", inline=True)
        embed.add_field(name="Queue:", value="```no data```", inline=True)
        embed.set_footer(text="Refreshes every 60 second")
        embed.timestamp = datetime.now()
        return embed

    swat_count = sum(p["type"] in ("unknown", "SWAT", "mentor") for p in matching_players)
    mentor_count = sum(p["type"] == "mentor" for p in matching_players)
    trainee_count = sum(p["type"] in ("trainee", "cadet") for p in matching_players)
    try:
        restart_val = fivem_data.get(region, {}).get("vars", {}).get("Time")
        if not restart_val:
            raise ValueError("Missing 'Time' field")
        restart_timer = time_convert(restart_val)
    except Exception as e:
        log("warning", f"No restart data for {region}: {e} -- raw data: {fivem_data.get(region)}")
        restart_timer = "*No restart data available!*"
    if mentor_count:
        val = ""
        for mp in matching_players:
            val += f"\n - {mp['username']} (<@{mp.get('discord_id','') }>)" if mp.get("discord_id") else f"\n - {mp['username']} (❔)"
        embed.add_field(name="Mentors Online:", value=val, inline=False)
    if swat_count - mentor_count > 0:
        val = ""
        for mp in matching_players:
            val += f"\n - {mp['username']} (<@{mp.get('discord_id','') }>)" if mp.get("discord_id") else f"\n - {mp['username']} (❔)"
        embed.add_field(name="SWAT Online:", value=val, inline=False)
    if trainee_count:
        val = ""
        for mp in matching_players:
            if mp["type"] == "trainee":
                val += f"\n {mp['username']} (<@{mp.get('discord_id','') }>)"
            elif mp["type"] == "cadet":
                val += f"\n {mp['username']} (<@{mp.get('discord_id','') }>)"
        embed.add_field(name="Cadets / Trainees Online:", value=val, inline=False)
    if all(p["type"] not in ("SWAT", "mentor", "trainee", "cadet", "unknown") for p in matching_players):
        embed.add_field(name="Nobody is online", value="", inline=False)
    if queue_data and region in queue_data:
        p = queue_data[region]
        embed.add_field(name="SWAT:", value=f"``` {swat_count} ```", inline=True)
        embed.add_field(name="Players:", value=f"```{p['Players']}/{p['MaxPlayers']}```", inline=True)
        embed.add_field(name="Queue:", value=f"```{p['QueuedPlayers']}```", inline=True)
        embed.add_field(name="", value=restart_timer, inline=False)
    else:
        embed.add_field(name="SWAT:", value=f"```{swat_count}```", inline=True)
        embed.add_field(name="Players:", value="```no data```", inline=True)
        embed.add_field(name="Queue:", value="```no data```", inline=True)
    embed.set_footer(text="Refreshes every 60 second")
    embed.timestamp = datetime.now()
    return embed

async def check_and_update_server_info(region):
    if region not in SERVERS_CONFIG:
        log("error", f"Region {region} not found in {SERVERS_CONFIG_FILE}.")
        return
    shortcut = SERVERS_CONFIG[region].get("shortcut")
    if not shortcut:
        log("error", f"No shortcut defined for region {region}.")
        return
    url = f"https://servers-frontend.fivem.net/api/servers/single/{shortcut}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                response.raise_for_status()
                data = await response.json()
        endpoints = data.get("Data", {}).get("connectEndPoints", [])
        if endpoints:
            new_endpoint = endpoints[0]
            if ":" in new_endpoint:
                new_ip, new_port = new_endpoint.split(":", 1)
                current_ip = SERVERS_CONFIG[region].get("ip")
                current_port = SERVERS_CONFIG[region].get("port")
                if new_ip != current_ip or new_port != current_port:
                    log("info", f"Server {region} info changed: {current_ip}:{current_port} -> {new_ip}:{new_port}")
                    SERVERS_CONFIG[region]["ip"] = new_ip
                    SERVERS_CONFIG[region]["port"] = new_port
                    SERVERS_CONFIG[region]["api_url"] = f"http://{new_ip}:{new_port}/info.json"
                    with open(SERVERS_CONFIG_FILE, "w") as f:
                        json.dump(SERVERS_CONFIG, f, indent=4)
                else:
                    log("info", f"Server {region} info remains unchanged.")
        else:
            log("warning", f"No endpoints found in FiveM API response for region {region}.")
    except Exception as e:
        log("error", f"Error checking FiveM server info for {region}: {e}")

# ------------------- Message Slot Update Functions -------------------
async def get_or_create_embed_slots(channel):
    stored = []
    if os.path.exists(EMBEDS_FILE) and os.path.getsize(EMBEDS_FILE) > 0:
        try:
            with open(EMBEDS_FILE, "r") as f:
                stored = json.load(f)
        except Exception as e:
            log("error", f"Error loading {EMBEDS_FILE}: {e}")
            stored = []
    if len(stored) != len(ORDERED_REGIONS):
        log("info", "Stored embed slots not found or incomplete. Creating new embed slots...")
        stored = []
        placeholder = discord.Embed(title="Placeholder", description="This message will be updated shortly.", colour=0x999999)
        for _ in ORDERED_REGIONS:
            msg = await channel.send(embed=placeholder)
            stored.append({
                "message_id": msg.id,
                "channel_id": msg.channel.id
            })
            await asyncio.sleep(1)
        with open(EMBEDS_FILE, "w") as f:
            json.dump(stored, f)
    return stored

async def update_embed_slots(channel, embed_list, stored_slots):
    for i, (region, embed_obj, _) in enumerate(embed_list):
        slot = stored_slots[i]
        try:
            msg = await channel.fetch_message(slot["message_id"])
            await msg.edit(embed=embed_obj)
            log("info", f"Updated slot {i} for region {region}.")
        except Exception as e:
            log("error", f"Error updating slot {i} for region {region}: {e}")
        await asyncio.sleep(1)

# ------------------- Main Update Loop -------------------
@tasks.loop(seconds=CHECK_INTERVAL)
async def update_game_status():
    log("info", "----- Starting update_game_status cycle -----")
    load_servers_config()
    await update_discord_cache()
    queue_data = await getqueuedata()
    fivem_data = await get_fivem_data()
    
    regions = ORDERED_REGIONS
    results = []
    for region in regions:
        players = await fetch_players(region)
        results.append(players)
        await asyncio.sleep(1)
    region_players_map = dict(zip(regions, results))
    
    for region in regions:
        players = region_players_map.get(region)
        if players is None or (fivem_data and fivem_data.get(region) is None):
            failure_counts[region] = failure_counts.get(region, 0) + 1
            log("warning", f"Failure count for region {region} increased to {failure_counts[region]}.")
            if failure_counts[region] >= 5:
                log("info", f"Failure count for {region} reached threshold; checking server info...")
                await check_and_update_server_info(region)
                failure_counts[region] = 0
        else:
            failure_counts[region] = 0

    embed_list = []
    for region in regions:
        players = region_players_map.get(region)
        matching_players = [] if players else None
        if isinstance(players, list):
            matching_players = []
            for pl in players:
                username = pl["Username"]["Username"]
                if any(mp["username"] == username for mp in matching_players):
                    continue
                if username.startswith("[SWAT] "):
                    cleaned_name = re.sub(r'^\[SWAT\]\s*', '', username, flags=re.IGNORECASE)
                    discord_found = False
                    for discord_name, details in discord_cache["members"].items():
                        compare_dn = re.sub(r'\s*\[SWAT\]$', '', discord_name, flags=re.IGNORECASE)
                        if cleaned_name.lower() == compare_dn.lower():
                            discord_found = True
                            mtype = "mentor" if MENTOR_ROLE_ID in details["roles"] else "SWAT"
                            matching_players.append({
                                "username": username,
                                "type": mtype,
                                "discord_id": details["id"],
                                "rank": get_rank_from_roles(details["roles"])
                            })
                            break
                    if not discord_found:
                        matching_players.append({
                            "username": username,
                            "type": "SWAT",
                            "discord_id": None,
                            "rank": None
                        })
                else:
                    for discord_name, details in discord_cache["members"].items():
                        tmp_dn = re.sub(r'\s*\[(CADET|TRAINEE|SWAT)\]$', '', discord_name, flags=re.IGNORECASE)
                        if username.lower() == tmp_dn.lower():
                            if CADET_ROLE_ID in details["roles"]:
                                matching_players.append({
                                    "username": username,
                                    "type": "cadet",
                                    "discord_id": details["id"],
                                    "rank": get_rank_from_roles(details["roles"])
                                })
                            elif TRAINEE_ROLE_ID in details["roles"]:
                                matching_players.append({
                                    "username": username,
                                    "type": "trainee",
                                    "discord_id": details["id"],
                                    "rank": get_rank_from_roles(details["roles"])
                                })
                            elif SWAT_ROLE_ID in details["roles"]:
                                matching_players.append({
                                    "username": username,
                                    "type": "SWAT",
                                    "discord_id": details["id"],
                                    "rank": get_rank_from_roles(details["roles"])
                                })
                            break
        if matching_players is not None:
            matching_players.sort(key=lambda x: RANK_HIERARCHY.index(x["rank"]) if x["rank"] in RANK_HIERARCHY else len(RANK_HIERARCHY))
        embed_obj = await create_embed(region, matching_players, queue_data, fivem_data)
        offline = False
        if matching_players is None or (fivem_data and fivem_data.get(region) is None):
            offline = True
        if region in TEST_OVERRIDE_STATUS:
            log("info", f"TEST OVERRIDE: Forcing region {region} to be " +
                ("offline" if TEST_OVERRIDE_STATUS[region] else "online") + ".")
            offline = TEST_OVERRIDE_STATUS[region]
        embed_list.append((region, embed_obj, offline))
    
    log("info", f"Embed list before sorting: {[ (r, 'OFFLINE' if off else 'ONLINE') for r,_,off in embed_list ]}")
    embed_list.sort(key=lambda x: (0 if x[2] else 1,
                                   ORDERED_REGIONS.index(x[0]) if x[0] in ORDERED_REGIONS else 999))
    log("info", f"Embed list after sorting: {[ (r, 'OFFLINE' if off else 'ONLINE') for r,_,off in embed_list ]}")
    
    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        log("error", f"Status channel {STATUS_CHANNEL_ID} not found.")
        return
    stored_slots = await get_or_create_embed_slots(channel)
    await update_embed_slots(channel, embed_list, stored_slots)
    
    log("info", "----- update_game_status cycle complete -----")

# ------------------- Bot Token Loader & Run -------------------
with open(TOKEN_FILE, "r") as file:
    TOKEN = file.read().strip()

try:
    client.run(TOKEN)
except Exception as e:
    log("critical", f"Bot error: {e}")
    sys.exit(1)
