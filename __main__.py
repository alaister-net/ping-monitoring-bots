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

bot = commands.Bot(help_command=None, test_guilds=[768837050161823774])
st_client = Speedtest()
loop = asyncio.get_event_loop()

public_ch = alert_ch = log_ch = last_checked = status_msg = alert_msg = None
running_speedtest = False
checks = [{}]*50

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} with name {name}')

@bot.event
async def on_message(msg):
    if msg.author.id != bot.user.id:
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
            await msg.channel.send(f'{index}:{name}:PONG:{round(bot.latency*1000)}')
        
        elif value == 'SPEEDTEST' and int(data[3]) == int(index):
            print('[INFO] Received speedtest request')
            result = await loop.run_in_executor(None, run_speedtest)
            await msg.channel.send(f"{index}:{name}:ST-RESULT:{result['download']}:{result['upload']}")

@bot.event
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
        'download': round(st_client.download() / 1000000, 2),
        'upload': round(st_client.upload(pre_allocate=False) / 1000000, 2),
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
        'node': checks[index].get('node', 'Node')  if node is None else node,
        'online': checks[index].get('online', False)  if online is None else online,
        'delay': checks[index].get('delay', 0)  if delay is None else delay,
        'latency': checks[index].get('latency', 0)  if latency is None else latency,
        'alerts': alerts,
        'download': checks[index].get('download', 0) if download is None else download,
        'upload': checks[index].get('upload', 0) if upload is None else upload,
        'last_speedtest': checks[index].get('last_speedtest', None) if last_speedtest is None else last_speedtest,
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
    await bot.wait_until_ready()
    
    if status_msg is None:
        global public_ch, alert_ch, log_ch
        
        public_ch = await bot.fetch_channel(public_id)
        alert_ch = await bot.fetch_channel(alert_id)
        log_ch = await bot.fetch_channel(log_id)
        
        if public_ch is None or alert_ch is None or log_ch is None:
            exit('Channel is None!')
        
        await public_ch.purge()

if name == 'MASTER':
    async def get_speedtest_nodes(i: disnake.AppCmdInter, inp: str):
        nodes = {}
    
        for check in checks:
            if not check:
                continue
            
            nodes[check['node']] = check['index']
    
        return nodes
    
    @bot.slash_command(name='speedtest', description='Test server node network speed')
    async def speedtest_cmd(i: disnake.AppCmdInter, target: int = commands.Param(autocomplete=get_speedtest_nodes)):
        if name != 'MASTER':
            return
        
        global running_speedtest
    
        if running_speedtest:
            embed = disnake.Embed(title='Another Speedtest is still running', color=disnake.Color.red())
            return await i.response.send_message(embed=embed, ephemeral=True)
        
        if checks[target]['last_speedtest'] and (time() - checks[target]['last_speedtest']) < 60*15:
            check = checks[target]
            embed = disnake.Embed(title=f"{check['node']} Speedtest Result (Cached)", color=disnake.Color.fuchsia(), timestamp=datetime.fromtimestamp(check['last_speedtest']))
            embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
            embed.add_field('Download', f"**{check['download']}** MB/s")
            embed.add_field('Upload', f"**{check['upload']}** MB/s")
            return await i.response.send_message(embed=embed)
        
        running_speedtest = True
    
        await i.response.send_message(content='Loading...')
        await log_ch.send(f'0:MASTER:SPEEDTEST:{target}')
    
        while checks[target]['last_speedtest'] is None or (time() - checks[target]['last_speedtest']) >= 60*15:
            await asyncio.sleep(5)
        
        check = checks[target]
        embed = disnake.Embed(title=f"{check['node']} Speedtest Result", color=disnake.Color.fuchsia(), timestamp=datetime.fromtimestamp(check['last_speedtest']))
        embed.set_footer(text=f'Alaister.net Ping Monitoring Bot', icon_url='https://alaister.net/hotlink-ok/alaister_net_icon.png')
        embed.add_field('Download', f"**{check['download']}** MB/s")
        embed.add_field('Upload', f"**{check['upload']}** MB/s")
    
        await i.edit_original_message(content='', embed=embed)
    
        running_speedtest = False

    checker.start()

bot.run(token)
