#!/usr/bin/env python3
import requests
import websockets
import logging
import logging.handlers
import json
import os
from dotenv import load_dotenv
from datetime import datetime, UTC
from contextlib import suppress
from pathlib import Path
import discord
from emoji import DISCORD_EMOJI

load_dotenv()
# use environ API to raise Exception if variable doesn't exist
SECRET = os.environ["SECRET"]
GUILD = os.environ["GUILD"]
CHANNEL = os.environ["CHANNEL"]
NUTAKU_ID = os.environ["NUTAKU_ID"]
SERVER_PREFIX = os.environ["SERVER_PREFIX"]
ALBUMS = Path.cwd().joinpath('albums')

def discord_handler():
    handler = logging.handlers.RotatingFileHandler(
        filename='discord.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,  # Rotate through 5 files
    )
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(formatter)
    return handler

def init_token() -> str:
    account = 'https://ntk-login-api.kokmm.net/api/auth/login/game_account'
    account_p = { "login_id": NUTAKU_ID, "login_type": 0, "access_token": "", "pw": NUTAKU_ID }
    login_req = requests.post(account, account_p)
    login_info = login_req.json()['response']
    account_id = login_info['account_id']
    session_id = login_info['session_id']
    login = f"https://ntk-login-api.kokmm.net/api/auth/login/user?nutaku_id={NUTAKU_ID}"
    login_p = { "server_prefix": SERVER_PREFIX, "account_id": account_id, "session_id": session_id }
    server_req = requests.post(login, login_p)
    return str(server_req.json()['response']['socket_token'])

class LibrarianSaint(discord.Client):
    def __init__(self):
        super().__init__(intents = discord.Intents.default())
        self.synced = False
        self.logger = logging.getLogger('discord')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(discord_handler())

    async def on_ready(self):
        self.logger.info(f"Discord bot has logged in as {self.user.name}")
    
    async def setup_hook(self):
        self.loop.create_task(self.relay_chat())

    async def relay_chat(self):
        # wait self.on_ready()
        await self.wait_until_ready()
        if not self.synced:
            # Nutaku™ King of Kinks EN Community discord
            self.guild = self.get_guild(int(GUILD))
            self.logger.info(f"{self.user.name} is connected to {self.guild}")
            # serves on world-chat channel
            self.channel = self.get_channel(int(CHANNEL))
            self.logger.info(f"{self.user.name} is serving on {self.channel}")
            self.synced = True

        while not self.is_closed():
            new_url = "wss://ntk-chat.kokmm.net/socket.io/?a={}&EIO=4&transport=websocket".format(init_token())
            async with websockets.connect(new_url) as ws:
                r = await ws.recv()
                self.logger.info(f"ws:recv: {r}")
                await ws.send('40')
                self.logger.info("ws:send: 40")
                #await ws.recv()
                #await ws.send('42["public message", "Hello World from discord.gg/king-of-kinks"]')

                while True:
                    msg = await ws.recv()
                    match msg[:2]:
                        case '2':
                            self.logger.debug("ws:recv: 2")
                            await ws.send('3')
                            self.logger.debug("ws:send: 3")
                        case '40':
                            self.logger.info(f"ws:recv: {msg}")
                        case '42':
                            try:
                                await self.send_message(msg) 
                            except Exception as e:
                                self.logger.error(f"{e}")
                        case '44':
                            self.logger.error(f"ws:recv: {msg}")
                            # break the loop
                            break
                        case _:
                            self.logger.error(f"ws:recv: {msg}")
                # close the websockets
                ws.close()
    
    async def send_message(self, response: str):
        # remove 42 from string, load the array into json
        array = json.loads(response[2:])
        match array[0]:
            # world channel
            case "receive message":
                sender = array[1]['sender']
                player_icon = "Pet{}_Album.png".format(sender['icon'][:4])
                for fname in os.listdir(ALBUMS):
                    if fname == player_icon:
                        full_path = ALBUMS.joinpath(fname)
                        file = discord.File(full_path, player_icon)
                #create_time = datetime.utcfromtimestamp(array[1]['msg_time']).strftime('%H:%M:%S')
                create_time = datetime.fromtimestamp(array[1]['msg_time'], UTC).strftime('%H:%M:%S')
                message = array[1]['message']
                self.logger.info(f"ws:world: {message}")
                # remove HTML attribute
                message = message.replace('<event=player, ', '<')
                # replace in-game emojis with discord emojis
                for e_id, emoji in DISCORD_EMOJI.items():
                    message = message.replace(e_id, emoji)

                # create embedded message
                embedded = discord.Embed(title=sender['username'], color=discord.Color.blue())
                embedded.set_thumbnail(url=f"attachment://{player_icon}")
                embedded.add_field(name="Server", value="S{}".format(int(sender['server']) - 100), inline=True)
                embedded.add_field(name="Level", value=sender['lv'], inline=True)
                embedded.add_field(name="VIP", value=sender['vip_level'], inline=True)
                embedded.add_field(name="Public Message", value=message, inline=False)
                embedded.set_footer(text=f"message sent at {create_time}")
                if file:
                    await self.channel.send(file=file, embed=embedded)
                else:
                    await self.channel.send(embed=embedded)
            case 'capture country':
                return
            case _:
                return

if __name__ == '__main__':
    with suppress(KeyboardInterrupt):
        LibrarianSaint().run(SECRET)

