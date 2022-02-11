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
checks = [{}]*50

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
        update_data(index=int(i), node=key, online=True, delay=int(diff.total_seconds() * 1000), latency=int(value))
        
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

def update_data(index: int, node: str = None, online: bool = None, delay: int = None, latency: int = None, alerts: dict = None):
    global checks
    
    if alerts is None:
        if not checks[index]:
            alerts = {
                'delay': 0,
                'latency': 0,
            }
        else:
            alerts = checks[index]['alerts']
    
    checks[index] = {
        'index': index,
        'node': checks[index]['node'] if node is None else node,
        'online': checks[index]['online'] if online is None else online,
        'delay': checks[index]['delay'] if delay is None else delay,
        'latency': checks[index]['latency'] if latency is None else latency,
        'alerts': alerts,
    }

@tasks.loop(seconds=60.0)
async def checker():
    global last_checked, status_msg, alert_msg, checks
    
    for check in checks:
        if not check:
            continue
        
        update_data(index=check['index'], online=False)
        
    try:
        msg = await private_ch.send('0:MASTER:PING')
    except Exception as e:
        print(e)
        await asyncio.sleep(5)
        await checker()
        return
    
    last_checked = msg.created_at.replace(tzinfo=None)
    
    await asyncio.sleep(10)
    
    embed = disnake.Embed(title='Node Status', color=disnake.Color.fuchsia(), timestamp=datetime.now())
    embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
    
    view = disnake.ui.View(timeout=None)
    view.add_item(disnake.ui.Button(label='System Status', url='https://status.alaister.net'))
    view.add_item(disnake.ui.Button(label='GitHub', url='https://github.com/alaister-net/ping-monitoring-bots'))
    
    alerts = []
    for check in checks:
        if not check:
            continue
        
        if check['online']:
            status = ':green_circle: ONLINE'
        else:
            status = ':warning: DISCORD API ERROR'
            alerts.append((check['node'], 'Discord API error'))
        
        embed.add_field(check['node'],
        f"`STATUS` **{status}** \n`MESSAGE RESPONSE DELAY` **{check['delay']}** ms \n`DISCORD API LATENCY` **{check['latency']}** ms",
        inline=False)
        
        counts = check.get('alerts', {
            'delay': 0,
            'latency': 0,
        })
        
        if check['delay'] >= 2000:
            counts['delay'] += 1
        elif counts['delay'] > 2:
            counts['delay'] -= 2
        else:
            counts['delay'] = 0
        
        if check['latency'] >= 1000:
            counts['latency'] += 1
        elif counts['latency'] > 2:
            counts['latency'] -= 2
        else:
            counts['latency'] = 0
        
        update_data(index=check['index'], alerts=counts)
        
        if counts['delay'] >= 3:
            alerts.append((check['node'], 'High message response delay'))
        
        if counts['latency'] >= 3:
            alerts.append((check['node'], 'High Discord API latency'))
    
    try:
        status_msg = await public_ch.send(embed=embed, view=view) if status_msg is None else await status_msg.edit(embed=embed)
    except Exception as e:
        print(e)
        await asyncio.sleep(5)
        await checker()
        return
    
    if alerts:
        msg_body = f'<@&{admin_id}>, **STATUS ALERTS:**'
        
        for alert in alerts:
            msg_body += f"\n{alert[1]} alert on {alert[0]} (<t:{int(time())}:R>)"
        
        try:
            alert_msg = await public_ch.send(msg_body) if alert_msg is None else await alert_msg.edit(content=msg_body)
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            await checker()
            return

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
