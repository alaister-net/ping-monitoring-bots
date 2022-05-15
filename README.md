# Ping Monitoring Bots

These bots are ideal for monitoring the status of the servers/nodes that host Discord bots.

## Features

- Measure the message response delay of the slave bot on your servers
- Measure the latency between the slave bots and the Discord API server
- Measure the download and upload speed of your servers
- Show a permanent status summary message in a channel
- Alert (ping) you (a role) when the slave bots are offline, not responding or taking long time to reply to messages from the master bot
- Lightweight, tiny file size, low CPU and RAM consumption

## Requirements

- One master server (multiple master servers not fully tested)
- At least one slave server or node
- Python 3.8 / 3.9 / 3.10

## Installation

Create a Discord bot in the Discord developer portal. You will need the bot token later.

**ALERT! Make sure the bot has the permission to READ and SEND messages in the three channels below. MESSAGE CONTENT INTENT is required.**

Download the files on all servers (both master and slave) you would like to monitor.

### Master Bot

On your master server,

```
pip install -U -r requirements.txt
cp .env.master .env
```

Edit the .env file.
- `LOG_FILE`: for storing Disnake logs
- `DISCORD_TOKEN`: the bot token **(You only need to create one bot user for the master bot and all slave bots!)**
- `GUILD_ID`: the ID of the guild where the channels below located
- `PUBLIC_CHANNEL`: the ID of the channel that sends the permanent status summary message
- `ALERT_CHANNEL`: the ID of the channel that sends the alert messages, can be same as the `PUBLIC_CHANNEL`
- `LOG_CHANNEL`: the ID of the channel that allows master and slave bots to communicate *(recommended to be hidden from non staff members)*
- `ADMIN_ROLE`: the ID of the role that will be pinged when something wrong with the slave bots/servers

Start the master bot
```
python master.py
```

### Slave Bot(s)

On your slave servers/nodes,

```
pip install -U -r requirements.txt
cp .env.slave .env
```

Edit the .env file. (some configurations are same as the master bot's .env file)
- `INDEX`: an integer that is **unique** across all slave bots; the lower the number, the higher priority it will be shown in the permanent status summary message
- `NAME`: a name representing the slave server

Start the slave bots
```
python slave.py
```
