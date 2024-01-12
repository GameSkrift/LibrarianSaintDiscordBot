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
from asynctinydb import TinyDB, Query
import discord
from emoji import DISCORD_EMOJI

load_dotenv()
# use environ API to raise Exception if variable doesn't exist
SECRET = os.environ["SECRET"]
GUILD = os.environ["GUILD"]
CHANNEL = os.environ["CHANNEL"]
STORAGE = os.environ["STORAGE"]
WSS_URI = "wss://ntk-chat.kokmm.net/socket.io/?a={}&EIO=4&transport=websocket"
ALBUMS = Path.cwd().joinpath('albums')
USER = Query()

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

class LibrarianSaint(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  
        super().__init__(intents=intents)
        self.synced = False
        self.logger = logging.getLogger('discord')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(discord_handler())
        self.db = TinyDB(STORAGE)

    async def on_ready(self):
        self.logger.info(f"Discord bot has logged in as {self.user.name}")

    async def on_message(self, message):
        if message.channel == self.channel and await self.db.contains(USER.user_id == str(message.author.id)):
            content = message.content
            if message.reference and message.reference.resolved.author.id == self.user.id:
                embed = message.reference.resolved.embeds[0]
                content = "<event=player, {}>@{} {}".format(embed.fields[2].value, embed.description, content)
            # create coroutine to avoid blocking
            self.loop.create_task(self.player_message_relay(str(message.author.id), content))
            await message.delete()
    
    async def setup_hook(self):
        # setup coroutine along with on_ready()
        self.loop.create_task(self.server_message_relay())

    async def player_message_relay(self, user_id, message):
        token = await self.verify_token(user_id)
        url = WSS_URI.replace('{}', token)
        async with websockets.connect(url) as ws:
            await ws.recv()
            await ws.send('40')
            await ws.recv()
            await ws.send(f"42[\"public message\", \"{message}\"]")

    async def server_message_relay(self):
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
            token = await self.verify_token('0')
            url = WSS_URI.replace('{}', token)
            async with websockets.connect(url) as ws:
                r = await ws.recv()
                self.logger.info(f"ws:recv: {r}")
                await ws.send('40')
                self.logger.info("ws:send: 40")
                #await ws.recv()
                #await ws.send('42["public message", "Hello World from discord.gg/king-of-kinks"]')

                while not self.is_closed():
                    try:
                        msg = await ws.recv()
                        match msg[:2]:
                            case '2':
                                self.logger.debug("ws:recv: 2")
                                await ws.send('3')
                                self.logger.debug("ws:send: 3")
                            case '40':
                                self.logger.info(f"ws:recv: {msg}")
                            case '42':
                                await self.write_message(msg) 
                            case '44':
                                self.logger.error(f"ws:recv: {msg}")
                                break
                            case _:
                                self.logger.warning(f"ws:recv: {msg}")
                    except Exception as e:
                        self.logger.error(f"ws:exception: {e}")
                        break
    
    async def write_message(self, response: str):
        # remove 42 from string, load the array into json
        array = json.loads(response[2:])
        match array[0]:
            # world channel
            case "receive message":
                sender = array[1]['sender']
                player_icon = "herocard_{}.jpg".format(sender['icon'][:4])
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
                embedded = discord.Embed(title="[KOK+{}] {}".format(int(sender['server']) - 100, sender['username']), description=sender['username'], color=discord.Color.blue())
                embedded.set_thumbnail(url=f"attachment://{player_icon}")
                embedded.add_field(name="Level", value=sender['lv'], inline=True)
                embedded.add_field(name="VIP", value=sender['vip_level'], inline=True)
                embedded.add_field(name="UUID", value=sender['user_id'], inline=False)
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

    async def verify_token(self, user_id) -> str:
        user_data = await self.db.get(USER.user_id == user_id)

        if datetime.now(UTC).timestamp() - user_data['create_time'] > 21600:
            self.logger.info(f"updating (User: {user_id}) token...")
            account = 'https://ntk-login-api.kokmm.net/api/auth/login/game_account'
            account_p = { "login_id": user_data['nutaku_id'], "login_type": 0, "access_token": "", "pw": user_data['nutaku_id']}
            login_req = requests.post(account, account_p)
            login_info = login_req.json()['response']
            account_id = login_info['account_id']
            session_id = login_info['session_id']
            login = "https://ntk-login-api.kokmm.net/api/auth/login/user?nutaku_id={}".format(user_data['nutaku_id'])
            login_p = { "server_prefix": user_data['prefix'], "account_id": account_id, "session_id": session_id }
            server_req = requests.post(login, login_p)
            new_token = str(server_req.json()['response']['socket_token'])
            new_ts = datetime.now(UTC).timestamp()
            await self.db.update({ 'token': new_token, 'create_time': new_ts }, USER.user_id == user_id)
            self.logger.info(f"(User: {user_id}) token has been updated.")

            return new_token
        else:
            return user_data['token']


if __name__ == '__main__':
    with suppress(KeyboardInterrupt):
        LibrarianSaint().run(SECRET)

