from os import getenv
from sys import exit
from datetime import datetime
from time import time
import asyncio
from dotenv import load_dotenv
import logging, disnake
from disnake.ext import commands, tasks
from speedtest import Speedtest

load_dotenv()
log_file = getenv('LOG_FILE')
token = getenv('DISCORD_TOKEN')
index = getenv('INDEX')
name = getenv('NAME')
public_id = getenv('PUBLIC_CHANNEL')
alert_id = getenv('ALERT_CHANNEL')
log_id = getenv('LOG_CHANNEL')
admin_id = getenv('ADMIN_ROLE')

logger = logging.getLogger('disnake')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename=log_file, encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

client = disnake.Client()
st_client = Speedtest()
loop = asyncio.get_event_loop()

public_ch = alert_ch = log_ch = last_checked = status_msg = alert_msg = None
running_speedtest = False
checks = [{}]*50

@client.event
async def on_ready():
    print(f'Logged in as {client.user} with name {name}')

@client.event
async def on_message(msg):
    if msg.author.id != client.user.id:
        return
    
    data = msg.content.split(':')
    
    if len(data) < 3:
        return
    
    i = data[0]
    key = data[1]
    value = data[2]
    
    if name == key:
        return
    
    if name == 'MASTER':
        if value == 'PONG':
            diff = msg.created_at.replace(tzinfo=None) - last_checked
            update_data(index=int(i), node=key, online=True, delay=int(diff.total_seconds() * 1000), latency=int(data[3]))
        
        elif value == 'ST-RESULT':
            update_data(index=int(i), node=key, online=True, download=float(data[3]), upload=float(data[4]), last_speedtest=time())
        
    elif key == 'MASTER':
        if value == 'PING':
            await msg.channel.send(f'{index}:{name}:PONG:{round(client.latency*1000)}')
        
        elif value == 'SPEEDTEST' and int(data[3]) == index:
            print('[INFO] Received speedtest request')
            result = await loop.run_in_executor(None, run_speedtest)
            await msg.channel.send(f'{index}:{name}:ST-RESULT:{result["download"]}:{result["upload"]}')

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
        if await alert_ch.fetch_message(alert_msg.id) is None:
            alert_msg = None
    except:
        alert_msg = None
        return

def run_speedtest():
    return {
        'download': round(st_client.download(threads=1) / 1000000, 2),
        'upload': round(st_client.upload(pre_allocate=False, threads=1) / 1000000, 2),
    }

def update_data(
    index: int, node: str = None, online: bool = None, delay: int = None, latency: int = None, alerts: dict = None,
    download: float = None, upload: float = None, last_speedtest: int = None,
):
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
        'download': checks[index]['download'] if download is None else download,
        'upload': checks[index]['upload'] if upload is None else upload,
        'last_speedtest': checks[index]['last_speedtest'] if last_speedtest is None else last_speedtest,
    }

@tasks.loop(seconds=30.0)
async def checker():
    global last_checked, status_msg, alert_msg, checks
    
    for check in checks:
        if not check:
            continue
        
        update_data(index=check['index'], online=False)
        
    try:
        msg = await log_ch.send('0:MASTER:PING')
    except Exception as e:
        print(e)
        await asyncio.sleep(3)
        await checker()
        return
    
    last_checked = msg.created_at.replace(tzinfo=None)
    
    await asyncio.sleep(5)
    
    embed = disnake.Embed(title='Node Status', color=disnake.Color.fuchsia(), timestamp=datetime.now())
    embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
    
    view = disnake.ui.View(timeout=None)
    view.add_item(disnake.ui.Button(label='System Status', url='https://alaister.net/status/'))
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
        
        if check['delay'] >= 1500:
            counts['delay'] += 1
        else:
            counts['delay'] = 0
        
        if check['latency'] >= 500:
            counts['latency'] += 1
        else:
            counts['latency'] = 0
        
        update_data(index=check['index'], alerts=counts)
        
        if counts['delay'] >= 2:
            alerts.append((check['node'], 'High message response delay'))
        
        if counts['latency'] >= 2:
            alerts.append((check['node'], 'High Discord API latency'))
    
    try:
        status_msg = await public_ch.send(embed=embed, view=view) if status_msg is None else await status_msg.edit(embed=embed)
    except Exception as e:
        print(e)
        await asyncio.sleep(5)
        await checker()
        return
    
    if alerts:
        msg_body = f"<@&{admin_id}> - **STATUS ALERTS** <t:{int(time())}:R>\n"
        
        for alert in alerts:
            msg_body += f"\n> {alert[0]}: **{alert[1]}**"
        
        try:
            alert_msg = await alert_ch.send(msg_body) if alert_msg is None else await alert_msg.edit(content=msg_body)
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            await checker()
            return

@checker.before_loop
async def before_check():
    await client.wait_until_ready()
    
    if status_msg is None:
        global public_ch, alert_ch, log_ch
        
        public_ch = await client.fetch_channel(public_id)
        alert_ch = await client.fetch_channel(alert_id)
        log_ch = await client.fetch_channel(log_id)
        
        if public_ch is None or alert_ch is None or log_ch is None:
            exit('Channel is None!')
        
        await public_ch.purge()

async def get_speedtest_nodes(i: disnake.AppCmdInter, inp: str):
    return {check['node']:check['index'] for check in checks}

if name == 'MASTER':
    @commands.slash_command(description='Test server node network speed')
    async def test_speed(i: disnake.AppCmdInter, target: int = commands.Param(autocomplete=get_speedtest_nodes)):
        if running_speedtest:
            embed = disnake.Embed(title='Another Speedtest is still running', color=disnake.Color.red(), timestamp=datetime.now())
            return await i.response.send_message(embed=embed, ephemeral=True)
        
        if checks['index']['last_speedtest'] < 60*15:
            check = checks['index']
            embed = disnake.Embed(title=f"{check['node']} Speedtest Result (Cached)", color=disnake.Color.fuchsia(), timestamp=datetime.fromtimestamp(checks['index']['last_speedtest']))
            embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
            embed.add_field('Download', f"**{check['download']}** MB/s")
            embed.add_field('Upload', f"**{check['upload']}** MB/s")
            return await i.response.send_message(embed=embed)
        
        running_speedtest = True

        await i.response.send_message(content='Loading...')
        await log_ch.send(f'0:MASTER:SPEEDTEST:{target}')

        while checks['index']['last_speedtest'] is None or checks['index']['last_speedtest'] >= 60*15:
            await asyncio.sleep(10)
        
        check = checks['index']
        embed = disnake.Embed(title=f"{check['node']} Speedtest Result", color=disnake.Color.fuchsia(), timestamp=datetime.fromtimestamp(checks['index']['last_speedtest']))
        embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
        embed.add_field('Download', f"**{check['download']}** MB/s")
        embed.add_field('Upload', f"**{check['upload']}** MB/s")

        await i.edit_original_message(embed=embed)

        running_speedtest = False

    checker.start()

client.run(token)
