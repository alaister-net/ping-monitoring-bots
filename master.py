from os import getenv
from sys import exit
from datetime import datetime
from time import time
import asyncio
from dotenv import load_dotenv
import logging, disnake
from disnake.ext import commands, tasks

VERSION = "1.1.2"

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

bot = commands.Bot(
    intents=disnake.Intents(guild_messages=True, message_content=True),
    help_command=None,
    test_guilds=[int(guild_id)],
)


class PingMonitoringBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.checks = {}
        self.public_ch = self.alert_ch = self.log_ch = None
        self.status_msg = self.alert_msg = self.admin_ping_msg = None
        self.last_checked = self.last_ping = self.last_speedtest = None
        self.to_ping = False

        self.checker.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as MASTER as '{bot.user}'")

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.id != self.bot.user.id:
            return

        data = msg.content.split(":")

        if len(data) < 3:
            return

        i = int(data[0])
        key = data[1]
        value = data[2]

        if key == "MASTER":
            return

        if self.checks.get(i) is None:
            self.checks[i] = {}
        
        if value == "PONG":
            speedtesting = (
                self.last_speedtest is not None and time() - self.last_speedtest < 60
            )
            self.checks[i]["node"] = key
            self.checks[i]["online"] = True
            self.checks[i]["delay"] = (
                self.checks[i].get("delay", 0)
                if speedtesting
                else int(
                    (
                        (msg.created_at.replace(tzinfo=None) - self.last_checked)
                        .total_seconds() - round(self.bot.latency)
                    ) * 1000
                )
            )
            self.checks[i]["latency"] = (
                self.checks[i].get("latency", 0)
                if speedtesting
                else int(data[3])
            )

        elif value == "ST-RESULT":
            self.checks[i]["node"] = key
            self.checks[i]["online"] = True
            self.checks[i]["download"] = float(data[3])
            self.checks[i]["upload"] = float(data[4])

    @commands.Cog.listener()
    async def on_message_delete(self, _):
        try:
            if await self.public_ch.fetch_message(self.status_msg.id) is None:
                self.status_msg = None
        except Exception:
            self.status_msg = None
        finally:
            return

        try:
            if await self.alert_ch.fetch_message(self.alert_msg.id) is None:
                self.alert_msg = None
        except Exception:
            self.alert_msg = None
        finally:
            return

        try:
            if await self.alert_ch.fetch_message(self.admin_ping_msg.id) is None:
                self.admin_ping_msg = None
        except Exception:
            self.admin_ping_msg = None
        finally:
            return

    @tasks.loop(seconds=30.0)
    async def checker(self):
        for index in self.checks.keys():
            self.checks[index]["online"] = False

        try:
            msg = await self.log_ch.send("0:MASTER:PING")
        except Exception as e:
            print(e)
            await asyncio.sleep(3)
            await self.checker()
            return

        self.last_checked = msg.created_at.replace(tzinfo=None)

        await asyncio.sleep(3)

        embed = disnake.Embed(
            title="Node Status", color=disnake.Color.fuchsia(), timestamp=datetime.now()
        )
        embed.set_footer(
            text=f"Alaister.net Ping Monitoring Bot v{VERSION}",
            icon_url="https://alaister.net/hotlink-ok/alaister_net_icon.png",
        )

        self.to_ping = False

        for index in sorted(self.checks):
            check = self.checks[index]

            embed.add_field(
                check.get("node", "Unnamed"),
                f"`STATUS` **{':green_circle: ONLINE' if check.get('online') else ':warning: DISCORD API ERROR'}**"
                + f"\n`MESSAGE RESPONSE DELAY` **{check.get('delay', '?') if check.get('online') else '?'}** ms"
                + f"\n`DISCORD API LATENCY` **{check.get('latency', '?') if check.get('online') else '?'}** ms"
                + f"\n`DOWNLOAD/UPLOAD SPEED` **{check.get('download', '?')}** / **{check.get('upload', '?')}** Mbps",
                inline=False,
            )

            alerts = check.get("alerts") or {"online": 0, "delay": 0, "latency": 0}
            alerts["online"] = (
                alerts["online"] + 1 if not check.get("online", False) else 0
            )
            alerts["delay"] = alerts["delay"] + 1 if check.get("delay", 0) >= 600 else 0
            alerts["latency"] = (
                alerts["latency"] + 1 if check.get("latency", 0) >= 200 else 0
            )

            alert_msg_body = ""

            if alerts["online"] >= 2:
                alert_msg_body += f"- **Discord API error** <t:{int(time())}:R>\n"

            if alerts["delay"] >= 2:
                alert_msg_body += (
                    f"- **High message response delay** <t:{int(time())}:R>\n"
                )

            if alerts["latency"] >= 2:
                alert_msg_body += (
                    f"- **High Discord API latency** <t:{int(time())}:R>\n"
                )

            self.to_ping = self.to_ping or alert_msg_body != ""

            self.checks[index]["alerts"] = alerts
            self.checks[index]["alert_msg_body"] = alert_msg_body or check.get("alert_msg_body", "")

        view = StatusView(self.start_speedtest)

        try:
            self.status_msg = (
                await self.public_ch.send(embed=embed, view=view)
                if self.status_msg is None
                else await self.status_msg.edit(embed=embed)
            )
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            await self.checker()
            return

        await self.send_alerts()

    @checker.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

        if self.status_msg is None:
            self.public_ch = await self.bot.fetch_channel(public_id)
            self.alert_ch = await self.bot.fetch_channel(alert_id)
            self.log_ch = await self.bot.fetch_channel(log_id)

            if self.public_ch is None or self.alert_ch is None or self.log_ch is None:
                exit("One or more text channels cannot be found!")

            await self.public_ch.purge()
            await self.alert_ch.purge()

    async def start_speedtest(self):
        if self.last_speedtest and (time() - self.last_speedtest) < 60 * 15:
            return int(self.last_speedtest + 60 * 15)

        await self.log_ch.send(f"0:MASTER:SPEEDTEST")

        self.last_speedtest = time()

        return True

    async def send_alerts(self):
        embed = disnake.Embed(
            title="Status Alerts",
            color=disnake.Color.dark_red(),
            timestamp=datetime.now(),
        )
        embed.set_footer(
            text=f"Alaister.net Ping Monitoring Bot v{VERSION}",
            icon_url="https://alaister.net/hotlink-ok/alaister_net_icon.png",
        )

        for index in sorted(self.checks):
            check = self.checks.get(index, {})

            embed.add_field(
                check.get("node", "Unnamed"),
                check.get("alert_msg_body")
                or "Hurray! There are no system issues currently.",
                inline=False,
            )

        try:
            self.alert_msg = (
                await self.alert_ch.send(
                    embed=embed, view=AlertsView(self.clear_alerts)
                )
                if self.alert_msg is None
                else await self.alert_msg.edit(embed=embed)
            )
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            await self.send_alerts()

        if self.to_ping and (
            not self.last_ping or (time() - self.last_ping) > (60 * 5 - 10)
        ):
            try:
                if self.admin_ping_msg:
                    await self.admin_ping_msg.delete()
                    self.admin_ping_msg = None

                self.admin_ping_msg = await self.alert_ch.send(f"<@&{admin_id}>")

                self.last_ping = time()
            except Exception as e:
                print(e)

    async def clear_alerts(self):
        for index in self.checks.keys():
            self.checks[index]["alerts"] = self.checks[index]["alert_msg_body"] = None

        if self.admin_ping_msg:
            await self.admin_ping_msg.delete()
            self.admin_ping_msg = None

        await self.send_alerts()


class StatusView(disnake.ui.View):
    def __init__(self, st_func: PingMonitoringBot.start_speedtest):
        super().__init__()

        self.timeout = None

        self.st_func = st_func

        self.add_item(
            disnake.ui.Button(label="System Status", url="https://status.alaister.net")
        )
        self.add_item(
            disnake.ui.Button(
                label="GitHub",
                url="https://github.com/alaister-net/ping-monitoring-bots",
            )
        )

    @disnake.ui.button(
        label="Run Speedtest", emoji="▶️", style=disnake.ButtonStyle.green
    )
    async def run_speedtest(self, _, i: disnake.MessageInteraction):
        st = await self.st_func()

        if st is True:
            embed = disnake.Embed(
                title="Running speedtest...",
                description=f"The result will be updated after a few minutes.",
                color=disnake.Color.green(),
            )
        else:
            embed = disnake.Embed(
                title="A speedtest has just recently finished.",
                description=f"Please try again <t:{st}:R>",
                color=disnake.Color.red(),
            )

        await i.response.send_message(embed=embed, ephemeral=True)


class AlertsView(disnake.ui.View):
    def __init__(self, clear_func: PingMonitoringBot.clear_alerts):
        super().__init__()

        self.timeout = None

        self.clear_func = clear_func

    @disnake.ui.button(label="Clear Alerts", emoji="❎", style=disnake.ButtonStyle.red)
    async def clear_alerts(self, _, i: disnake.MessageInteraction):
        await self.clear_func()

        embed = disnake.Embed(
            title="Done!",
            description=f"All alerts and mentions have been cleared.",
            color=disnake.Color.green(),
        )
        await i.response.send_message(embed=embed, ephemeral=True)


bot.add_cog(PingMonitoringBot(bot))
bot.run(token)
