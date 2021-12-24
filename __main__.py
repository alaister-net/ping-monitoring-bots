from os import getenv
from sys import exit
from datetime import datetime
from dotenv import load_dotenv
import logging, disnake
from disnake.ext import tasks

load_dotenv()
log_file = getenv('LOG_FILE')
token = getenv('DISCORD_TOKEN')
name = getenv('NAME')
public_id = getenv('PUBLIC_CHANNEL')
private_id = getenv('PRIVATE_CHANNEL')
admin_id = getenv('ADMIN_ROLE')

logger = logging.getLogger('disnake')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename=log_file, encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

client = disnake.Client()

public_ch = None
private_ch = None
checks = {}
last_checked = None
last_alert = None
status_msg = None
alert_msg = None

@client.event
async def on_ready():
    print(f'Logged in as {client.user} with name {name}')

@client.event
async def on_message(msg):
    if msg.author.id != client.user.id:
        return
    
    data = msg.content.split(':', 1)
    
    if len(data) != 2:
        return
    
    key = data[0]
    value = data[1]
    
    if name == key:
        return
    
    if name == 'MASTER':
        global checks
        diff =  msg.created_at.replace(tzinfo=None) - last_checked
        checks[key] = {
            'ping': int(diff.total_seconds() * 1000),
            'latency': int(value),
        }
        await update_data()
    elif key == 'MASTER':
        if value == 'PING':
            await msg.channel.send(f'{name}:{round(client.latency*1000)}')

@client.event
async def on_message_delete(msg):
    global status_msg, alert_msg
    if msg.id == status_msg.id:
        status_msg = None
    elif msg.id == alert_msg.id:
        alert_msg = None

async def update_data():
    global status_msg, alert_msg
    
    embed = disnake.Embed(title='Node Status (for Discord bots)', color=disnake.Color.fuchsia(), timestamp=datetime.now())
    embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
    
    view = disnake.ui.View(timeout=None)
    view.add_item(disnake.ui.Button(label='System Status', url='https://status.alaister.net'))
    view.add_item(disnake.ui.Button(label='GitHub', url='https://github.com/alaister-net/ping-monitoring-bots'))
    
    alert = False
    titles = ('Node', 'Bot Ping', 'API Latency')
    
    for node, data in checks.items():
        embed.add_field(titles[0], node)
        embed.add_field(titles[1], str(data['ping']) + ' ms')
        embed.add_field(titles[2], str(data['latency']) + ' ms')
        
        if data['ping'] >= 3000 or data['latency'] >= 1500:
            alert = True
        titles = ('\u200b', '\u200b', '\u200b')
    
    status_msg = await public_ch.send(embed=embed, view=view) if status_msg is None else await status_msg.edit(embed=embed)
    if alert and alert_msg is None:
        alert_msg = await public_ch.send(f'<@&{admin_id}> High ping/latency alert!')

@tasks.loop(seconds=60.0)
async def checker():
    global last_checked
    last_checked = datetime.now()
    await private_ch.send('MASTER:PING')

@checker.before_loop
async def before_check():
    await client.wait_until_ready()
    if status_msg is None:
        global public_ch, private_ch
        public_ch = await client.fetch_channel(public_id)
        private_ch = await client.fetch_channel(private_id)
        if public_ch is None or private_ch is None:
            exit('Channel is None!')
        await public_ch.purge()

if name == 'MASTER':
    checker.start()

client.run(token)
