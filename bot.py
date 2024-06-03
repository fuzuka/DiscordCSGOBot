import discord
from discord.ext import commands, tasks
import socket
import json
import os
import requests
import a2s
import asyncio

with open('config.json', 'r') as f:
    config = json.load(f)

TOKEN = config['token']
COMMAND_PREFIX = config['command_prefix']
SERVERS = config['servers']
STATUS_CHANNEL_ID = config['status_channel_id']
MAPS_PATH = config['maps_path']
IPINFO_TOKEN = config['ipinfo_token']

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

def save_embeds(embeds):
    with open('embeds.txt', 'w') as f:
        for server_id, message_id in embeds.items():
            f.write(f"{server_id}:{message_id}\n")

def load_embeds():
    embeds = {}
    if os.path.exists('embeds.txt'):
        with open('embeds.txt', 'r') as f:
            for line in f:
                server_id, message_id = line.strip().split(':')
                embeds[server_id] = int(message_id)
    return embeds

async def get_server_region(ip):
    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json?token={IPINFO_TOKEN}")
        if response.status_code == 200:
            data = response.json()
            country = data.get('country', 'Unknown')
            if country == 'RU':
                return '🇷🇺 Россия'
            elif country == 'US':
                return '🇺🇸 США'
            elif country == 'FR':
                return '🇫🇷 Франция'
            elif country == 'CN':
                return '🇨🇳 Китай'
            elif country == 'UK':
                return '🇬🇧 Великобритания'
            elif country == 'DE':
                return '🇩🇪 Германия'
            elif country == 'JP':
                return '🇯🇵 Япония'
            elif country == 'IT':
                return '🇮🇹 Италия'
            elif country == 'IN':
                return '🇮🇳 Индия'
            else:
                return 'Неизвестно'
    except Exception as e:
        print(f"Error retrieving server region: {str(e)}")
    return 'Неизвестно'

def check_server_status(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((ip, port))
        if result == 0:
            return True
        else:
            return False
    except Exception as e:
        print(f"Error occurred while checking server status: {e}")
        return False
    finally:
        sock.close()

async def update_server_status(channel, server, embeds):
    address = (server['ip'], server['port'])
    try:
        online = check_server_status(server['ip'], server['port'])
        info = None
        players = []
        map_name = "unknown"
        map_image_path = os.path.join(MAPS_PATH, "unknown.png")

        if online:
            info = a2s.info(address)
            players = a2s.players(address)
            map_name = info.map_name if info else "unknown"

            potential_map_image_path = os.path.join(MAPS_PATH, f"{map_name}.png")
            if os.path.exists(potential_map_image_path):
                map_image_path = potential_map_image_path

        embed = discord.Embed(
            title=server['name'],
            description=f"**Статус**: {'Онлайн :green_circle:' if online else 'Оффлайн :red_circle:'}\n \nIP: {server['ip']}:{server['port']}\nПодключение: {server['connect_link']}",
            color=discord.Color.green() if online else discord.Color.red()
        )

        if online:
            embed.description += f"\nКарта: {map_name}"

            player_names = "\n".join([player.name for player in players]) if players else "*Нет игроков*"
            embed.add_field(name="Игроки:", value=player_names, inline=False)

        region = await get_server_region(server['ip'])
        embed.add_field(name=f"Местоположение сервера: {region}", value="\u200b", inline=True)

        embed.set_image(url=f"attachment://{os.path.basename(map_image_path)}")

        message_id = embeds.get(f"{server['name']}.png")
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    print(f"Rate limited. Retrying in {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed, file=discord.File(map_image_path))
            embeds[f"{server['name']}.png"] = message.id
            save_embeds(embeds)

    except Exception as e:
        print(f"Ошибка получения информации о сервере: {str(e)}")

@bot.event
async def on_ready():
    print(f'Бот готов. Зашёл как {bot.user}')
    update_status.start()

@tasks.loop(seconds=10)
async def update_status():
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    embeds = load_embeds()
    for server in SERVERS:
        await update_server_status(channel, server, embeds)

@bot.command()
@commands.has_permissions(administrator=True)
async def add(ctx, name: str, ip: str, port: int, connect_link: str):
    server = {
        "name": name,
        "ip": ip,
        "port": port,
        "connect_link": connect_link
    }
    SERVERS.append(server)
    config['servers'] = SERVERS
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)
    await ctx.send(f"Сервер {name} добавлен.")

@bot.command()
async def status(ctx, ip: str, port: int):
    server = next((s for s in SERVERS if s['ip'] == ip and s['port'] == port), None)
    if not server:
        await ctx.send("Сервер не найден.")
        return

    await update_server_status(ctx.channel, server, {})

bot.run(TOKEN)
