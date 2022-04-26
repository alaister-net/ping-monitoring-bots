from os import getenv
import asyncio
from dotenv import load_dotenv
import logging, disnake
from speedtest import Speedtest

load_dotenv()
log_file = getenv("LOG_FILE")
token = getenv("DISCORD_TOKEN")
index = getenv("INDEX")
name = getenv("NAME")

logger = logging.getLogger("disnake")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename=log_file, encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

bot = disnake.Client()
st_client = Speedtest()
loop = asyncio.get_event_loop()


@bot.event
async def on_ready():
    print(f"Logged in as SLAVE as '{name}' as '{bot.user}'")


@bot.event
async def on_message(msg):
    if msg.author.id != bot.user.id:
        return

    data = msg.content.split(":")

    if len(data) < 3:
        return

    key = data[1]
    value = data[2]

    if key == "MASTER":
        try:
            if value == "PING":
                await msg.channel.send(f"{index}:{name}:PONG:{round(bot.latency * 1000)}")

            elif value == "SPEEDTEST":
                result = await loop.run_in_executor(None, run_speedtest)
                await msg.channel.send(
                    f"{index}:{name}:ST-RESULT:{result['download']}:{result['upload']}"
                )
        
        except Exception as e:
            print(e)


def run_speedtest():
    return {
        "download": round(st_client.download() / 1000000, 2),
        "upload": round(st_client.upload(pre_allocate=False) / 1000000, 2),
    }


bot.run(token)
