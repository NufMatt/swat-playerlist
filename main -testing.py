import discord
from discord.ext import tasks, commands
import requests
import asyncio
import json
from datetime import datetime, timedelta
import pytz
import re

# Bot Setup
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

# Configurations
TESTING = True
USE_LOCAL_JSON = False
LOCAL_JSON_FILE = "json-formatting.json"
CACHE_UPDATE_INTERVAL = 300
CHECK_INTERVAL = 60

API_URLS = {
    "EU1": "https://api.gtacnr.net/cnr/players?serverId=EU1",
    "EU2": "https://api.gtacnr.net/cnr/players?serverId=EU2",
    "NA1": "https://api.gtacnr.net/cnr/players?serverId=US1",
    "NA2": "https://api.gtacnr.net/cnr/players?serverId=US2",
    "SEA": "https://api.gtacnr.net/cnr/players?serverId=SEA",
}

if TESTING:
    STATUS_CHANNEL_ID = 1320463232128913551
    GUILD_ID = 1300519755622383689
    MENTOR_ROLE_ID = 1303048285040410644
    CADET_ROLE_ID = 962226985222959145
    TRAINEE_ROLE_ID = 1033432392758722682
else:
    STATUS_CHANNEL_ID = 1322097975324971068
    GUILD_ID = 958271853158350850
    MENTOR_ROLE_ID = 1303048285040410644
    CADET_ROLE_ID = 962226985222959145
    TRAINEE_ROLE_ID = 1033432392758722682

# Utilities
def log(content):
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] {content}")

def fetch_json(url, verify_ssl=True):
    try:
        response = requests.get(url, verify=verify_ssl)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        log(f"Error fetching data from {url}: {e}")
        return None

# Discord Cache
class DiscordCache:
    def __init__(self):
        self.timestamp = None
        self.members = {}

    async def update(self):
        now = datetime.now()
        if self.timestamp and now - self.timestamp < timedelta(seconds=CACHE_UPDATE_INTERVAL):
            log("Discord cache is up-to-date.")
            return

        guild = client.get_guild(GUILD_ID)
        if not guild:
            log(f"Bot is not in a server with ID {GUILD_ID}.")
            return

        self.members = {
            member.display_name: {
                "id": member.id,
                "roles": [role.id for role in member.roles]
            } for member in guild.members
        }
        self.timestamp = now
        log("Discord cache updated.")

# Main Tasks
@tasks.loop(seconds=CHECK_INTERVAL)
async def update_game_status():
    cache = DiscordCache()
    await cache.update()

    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        log(f"Status channel with ID {STATUS_CHANNEL_ID} not found.")
        return

    for region, api_url in API_URLS.items():
        players = fetch_json(api_url)
        if not players:
            continue

        matching_players = []
        for player in players:
            username = player.get("Username", {}).get("Username", "")
            cleaned_username = re.sub(r"^\[SWAT\]\s*|\s*\[SWAT\]$", "", username)
            
            discord_member = next(
                (
                    {
                        "username": name,
                        "type": "mentor" if MENTOR_ROLE_ID in details["roles"] else "SWAT",
                        "discord_id": details["id"]
                    }
                    for name, details in cache.members.items()
                    if name.lower() == cleaned_username.lower()
                ),
                None
            )

            if discord_member:
                matching_players.append(discord_member)
            else:
                matching_players.append({"username": username, "type": "SWAT", "discord_id": None})

        # Create and send embed
        embed = discord.Embed(title=f"Region: {region}", color=0x00FF00 if matching_players else 0xFF0000)
        if matching_players:
            swat_count = len([p for p in matching_players if p["type"] == "SWAT"])
            embed.add_field(name="SWAT Members", value=str(swat_count))
        else:
            embed.add_field(name="Status", value="No data available")
        await channel.send(embed=embed)

# Events
@client.event
async def on_ready():
    log(f"Bot is online as {client.user}")
    update_game_status.start()

# Run the Bot
with open("token-test.txt" if TESTING else "token.txt", "r") as file:
    TOKEN = file.read().strip()

client.run(TOKEN)
