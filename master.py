from os import getenv
from sys import exit
from datetime import datetime
from time import time
import asyncio
from dotenv import load_dotenv
import logging, disnake
from disnake.ext import commands, tasks

VERSION = "1.0.0"

load_dotenv()
log_file = getenv("LOG_FILE")
token = getenv("DISCORD_TOKEN")
guild_id = getenv("GUILD_ID")
public_id = getenv("PUBLIC_CHANNEL")
alert_id = getenv("ALERT_CHANNEL")
log_id = getenv("LOG_CHANNEL")
admin_id = getenv("ADMIN_ROLE")

logger = logging.getLogger("disnake")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename=log_file, encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

bot = commands.Bot(help_command=None, test_guilds=[int(guild_id)])

ALERT_FORMAT = {"online": 0, "delay": 0, "latency": 0}
public_ch = (
    alert_ch
) = (
    log_ch
) = (
    last_checked
) = status_msg = alert_msg = admin_ping_msg = last_ping = last_speedtest = None
to_ping = False
checks = [{}] * 50


@bot.event
async def on_ready():
    print(f"Logged in as MASTER as '{bot.user}'")


@bot.event
async def on_message(msg):
    if msg.author.id != bot.user.id:
        return

    data = msg.content.split(":")

    if len(data) < 3:
        return

    i = data[0]
    key = data[1]
    value = data[2]

    if key == "MASTER":
        return

    if value == "PONG":
        speedtesting = last_speedtest is not None and time() - last_speedtest < 50
        update_data(
            index=int(i),
            node=key,
            online=True,
            delay=None
            if speedtesting
            else int(
                (
                    (msg.created_at.replace(tzinfo=None) - last_checked).total_seconds()
                    - round(bot.latency)
                )
                * 1000
            ),
            latency=None if speedtesting else int(data[3]),
        )

    elif value == "ST-RESULT":
        update_data(
            index=int(i),
            node=key,
            online=True,
            download=float(data[3]),
            upload=float(data[4]),
        )


@bot.event
async def on_message_delete(_):
    global status_msg
    try:
        if await public_ch.fetch_message(status_msg.id) is None:
            status_msg = None
    except Exception as _:
        status_msg = None
    finally:
        return

    global alert_msg
    try:
        if await alert_ch.fetch_message(alert_msg.id) is None:
            alert_msg = None
    except Exception as _:
        alert_msg = None
    finally:
        return

    global admin_ping_msg
    try:
        if await alert_ch.fetch_message(admin_ping_msg.id) is None:
            admin_ping_msg = None
    except Exception as _:
        admin_ping_msg = None
    finally:
        return


@tasks.loop(seconds=30.0)
async def checker():
    global last_checked, status_msg, checks, to_ping

    for check in checks:
        if not check:
            continue

        check["online"] = False

    try:
        msg = await log_ch.send("0:MASTER:PING")
    except Exception as e:
        print(e)
        await asyncio.sleep(3)
        await checker()
        return

    last_checked = msg.created_at.replace(tzinfo=None)

    await asyncio.sleep(3)

    embed = disnake.Embed(
        title="Node Status", color=disnake.Color.fuchsia(), timestamp=datetime.now()
    )
    embed.set_footer(
        text=f"Alaister.net Ping Monitoring Bot v{VERSION}",
        icon_url="https://alaister.net/hotlink-ok/alaister_net_icon.png",
    )

    view = StatusView()
    view.add_item(
        disnake.ui.Button(label="System Status", url="https://status.alaister.net")
    )
    view.add_item(
        disnake.ui.Button(
            label="GitHub", url="https://github.com/alaister-net/ping-monitoring-bots"
        )
    )

    for check in checks:
        if not check:
            continue

        embed.add_field(
            check["node"],
            f"`STATUS` **{':green_circle: ONLINE' if check['online'] else ':warning: DISCORD API ERROR'}**"
            + f"\n`MESSAGE RESPONSE DELAY` **{check['delay'] if check['online'] else '[NO DATA]'}** ms"
            + f"\n`DISCORD API LATENCY` **{check['latency'] if check['online'] else '[NO DATA]'}** ms"
            + f"\n`DOWNLOAD SPEED` **{check['download'] or '[NO DATA]'}** MB/s"
            + f"\n`UPLOAD SPEED` **{check['upload'] or '[NO DATA]'}** MB/s",
            inline=False,
        )

        check["alerts"]["online"] = (
            check["alerts"]["online"] + 1 if not check["online"] else 0
        )
        check["alerts"]["delay"] = (
            check["alerts"]["delay"] + 1 if check["delay"] >= 1000 else 0
        )
        check["alerts"]["latency"] = (
            check["alerts"]["latency"] + 1 if check["latency"] >= 1000 else 0
        )

        alert_msg_body = ""

        if check["alerts"]["online"] >= 2:
            alert_msg_body += f"- **Discord API error** <t:{int(time())}:R>\n"

        if check["alerts"]["delay"] >= 2:
            alert_msg_body += f"- **High message response delay** <t:{int(time())}:R>\n"

        if check["alerts"]["latency"] >= 2:
            alertmsg += f"- **High Discord API latency** <t:{int(time())}:R>\n"
        
        to_ping = alert_msg_body != ""

        update_data(
            index=check["index"], alerts=check["alerts"], alert_msg_body=alert_msg_body
        )

    try:
        status_msg = (
            await public_ch.send(embed=embed, view=view)
            if status_msg is None
            else await status_msg.edit(embed=embed)
        )
    except Exception as e:
        print(e)
        await asyncio.sleep(5)
        await checker()
        return

    await send_alert()


@checker.before_loop
async def before_check():
    await bot.wait_until_ready()

    if status_msg is None:
        global public_ch, alert_ch, log_ch

        public_ch = await bot.fetch_channel(public_id)
        alert_ch = await bot.fetch_channel(alert_id)
        log_ch = await bot.fetch_channel(log_id)

        if public_ch is None or alert_ch is None or log_ch is None:
            exit("Channel is None!")

        await public_ch.purge()
        await alert_ch.purge()
        await log_ch.purge(limit=10000)


def update_data(
    index: int,
    node: str = None,
    online: bool = None,
    delay: int = None,
    latency: int = None,
    download: float = None,
    upload: float = None,
    alerts: dict = None,
    alert_msg_body: str = None,
):
    global checks

    checks[index] = {
        "index": index,
        "node": node or checks[index].get("node", f"NODE #{index}"),
        "online": checks[index].get("online", False) if online is None else online,
        "delay": delay or checks[index].get("delay", 0),
        "latency": latency or checks[index].get("latency", 0),
        "download": download or checks[index].get("download", 0),
        "upload": upload or checks[index].get("upload", 0),
        "alerts": alerts or checks[index].get("alerts", ALERT_FORMAT),
        "alert_msg_body": alert_msg_body or checks[index].get("alert_msg_body"),
    }


async def send_alert():
    global checks, alert_msg, admin_ping_msg, last_ping, to_ping

    embed = disnake.Embed(
        title="Status Alerts", color=disnake.Color.dark_red(), timestamp=datetime.now()
    )
    embed.set_footer(
        text=f"Alaister.net Ping Monitoring Bot v{VERSION}",
        icon_url="https://alaister.net/hotlink-ok/alaister_net_icon.png",
    )

    for check in checks:
        if not check:
            continue

        embed.add_field(
            check["node"],
            check["alert_msg_body"] or "No records have been found.",
            inline=False,
        )

    try:
        alert_msg = (
            await alert_ch.send(embed=embed, view=AlertsView())
            if alert_msg is None
            else await alert_msg.edit(embed=embed)
        )
    except Exception as e:
        print(e)
        await asyncio.sleep(5)
        await send_alert()

    if to_ping and (not last_ping or (time() - last_ping) > (60 * 5 - 10)):
        try:
            if admin_ping_msg:
                await admin_ping_msg.delete()
                admin_ping_msg = None

            admin_ping_msg = await alert_ch.send(f"<@&{admin_id}>")

            last_ping = time()
        except Exception as e:
            print(e)


class StatusView(disnake.ui.View):
    def __init__(self):
        super().__init__()

        self.timeout = None

    @disnake.ui.button(
        label="Run Speedtest", emoji="▶️", style=disnake.ButtonStyle.green
    )
    async def run_speedtest(self, _, i: disnake.MessageInteraction):
        global checks, last_speedtest

        for check in checks:
            if not check:
                continue

        if last_speedtest and (time() - last_speedtest) < 60 * 15:
            embed = disnake.Embed(
                title="A speedtest has just recently finished.",
                description=f"Please try again <t:{int(last_speedtest + 60*15)}:R>",
                color=disnake.Color.red(),
            )
            return await i.response.send_message(embed=embed, ephemeral=True)

        embed = disnake.Embed(
            title="Running speedtest...",
            description=f"The result will be updated after a few minutes.",
            color=disnake.Color.green(),
        )
        await i.response.send_message(embed=embed, ephemeral=True)

        await log_ch.send(f"0:MASTER:SPEEDTEST")

        last_speedtest = time()


class AlertsView(disnake.ui.View):
    def __init__(self):
        super().__init__()

        self.timeout = None

    @disnake.ui.button(label="Clear Alerts", emoji="❎", style=disnake.ButtonStyle.red)
    async def clear_alerts(self, _, i: disnake.MessageInteraction):
        global checks, admin_ping_msg

        for check in checks:
            if not check:
                continue

            check["alerts"] = ALERT_FORMAT
            check["alert_msg_body"] = None

        embed = disnake.Embed(
            title="Done!",
            description=f"All alerts and mentions have been cleared.",
            color=disnake.Color.green(),
        )
        await i.response.send_message(embed=embed, ephemeral=True)

        if admin_ping_msg:
            await admin_ping_msg.delete()
            admin_ping_msg = None

        await send_alert()


checker.start()
bot.run(token)
