from os import getenv
from sys import exit
from datetime import datetime
from time import time
import asyncio
from dotenv import load_dotenv
import logging, disnake
from disnake.ext import tasks

load_dotenv()
log_file = getenv('LOG_FILE')
token = getenv('DISCORD_TOKEN')
index = getenv('INDEX')
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

public_ch = private_ch = last_checked = status_msg = alert_msg = None
checks = [None]*50
alerted_checks = {}

@client.event
async def on_ready():
    print(f'Logged in as {client.user} with name {name}')

@client.event
async def on_message(msg):
    if msg.author.id != client.user.id:
        return
    
    data = msg.content.split(':')
    
    if len(data) != 3:
        return
    
    i = data[0]
    key = data[1]
    value = data[2]
    
    if name == key:
        return
    
    if name == 'MASTER':
        global checks
        diff = msg.created_at.replace(tzinfo=None) - last_checked
        checks[int(i)] = {
            'node': key,
            'ping': int(diff.total_seconds() * 1000),
            'latency': int(value),
        }
        
    elif key == 'MASTER':
        if value == 'PING':
            await msg.channel.send(f'{index}:{name}:{round(client.latency*1000)}')

@client.event
async def on_message_delete(_):
    if name != 'MASTER':
        return
    
    global status_msg
    try:
        if await public_ch.fetch_message(status_msg.id) is None:
            status_msg = None
    except:
        status_msg = None
        return
    
    global alert_msg
    try:
        if await public_ch.fetch_message(alert_msg.id) is None:
            alert_msg = None
    except:
        alert_msg = None
        return

@tasks.loop(seconds=60.0)
async def checker():
    global last_checked, status_msg, alert_msg, alerted_checks
    msg = await private_ch.send('0:MASTER:PING')
    last_checked = msg.created_at.replace(tzinfo=None)
    
    await asyncio.sleep(6)
    
    embed = disnake.Embed(title='Node Status (for Discord bots)', color=disnake.Color.fuchsia(), timestamp=datetime.now())
    embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
    
    view = disnake.ui.View(timeout=None)
    view.add_item(disnake.ui.Button(label='System Status', url='https://status.alaister.net'))
    view.add_item(disnake.ui.Button(label='GitHub', url='https://github.com/alaister-net/ping-monitoring-bots'))
    
    alerts = []
    for check in checks:
        if check is None:
            continue
        
        embed.add_field(check['node'], f"`BOT PING` **{check['ping']}** ms \n`API LATENCY` **{check['latency']}** ms", inline=False)
        
        count = alerted_checks.get(check['node'], 0)
        if check['ping'] >= 2000 or check['latency'] >= 1000:
            alerted_checks[check['node']] = count + 1
        elif count > 1:
            alerted_checks[check['node']] = count - 1
        else:
            alerted_checks[check['node']] = 0
    
    status_msg = await public_ch.send(embed=embed, view=view) if status_msg is None else await status_msg.edit(embed=embed)
    
    alerts = []
    for alerted_node, count in alerted_checks.items():
        if count >= 3:
            alerts.append(check['node'])
    
    if alerts:
        msg_body = f'<@&{admin_id}>, high ping/latency alert on {", ".join(alerts)} (<t:{int(time())}:R>)'
        alert_msg = await public_ch.send(msg_body) if alert_msg is None else await alert_msg.edit(content=msg_body)

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
