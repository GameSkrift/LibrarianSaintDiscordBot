#!/usr/bin/env python3
import websockets
import logging
import logging.handlers
import json
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from datetime import datetime
from contextlib import suppress
from pathlib import Path
from asynctinydb import TinyDB, Query
import aiohttp
import discord
from emoji import KOK_EMOJI, UNICODE_EMOJI

load_dotenv()
# use environ API to raise Exception if variable doesn't exist
SECRET = os.environ["SECRET"]
GUILD = os.environ["SERVER"]
PUBLIC_CHANNEL = os.environ["CHANNEL"]
SUBSCRIBER_LIST = os.environ["STORAGE"]
GUILD_CHANNELS = os.environ["GUILD_CHANNELS"]
GUILD_LIST = os.environ["GUILD_LIST"]
WSS_URI = "wss://ntk-chat.kokmm.net/socket.io/?a={}&EIO=4&transport=websocket"
ALBUMS = Path.cwd().joinpath('albums')
SERVER_TZ = ZoneInfo(key='America/Puerto_Rico')
USER = Query()

class LibrarianSaint(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  
        super().__init__(intents=intents)
        self.logger = logging.getLogger('discord')
        self.logger.setLevel(logging.INFO)
        self.subscriber_list = TinyDB(SUBSCRIBER_LIST)
        self.sync_guild = False

    async def on_ready(self) -> None:
        self.logger.info(f"Discord bot has logged in as {self.user.name}")

    async def on_message(self, message) -> None:
        bot_message = True if message.author.id == self.user.id else False
        news_channel = True if message.channel.type == discord.ChannelType.news else False
        if message.channel == self.public_channel:
            if bot_message:
                if news_channel:
                    # publish the message on news channel
                    await message.publish()
            elif await self.subscriber_list.contains(USER.user_id == str(message.author.id)):
                content = message.content.replace('\"', '*')
                await message.delete()
                # user can only reply to bot message
                if message.mentions:
                    if message.reference and message.reference.resolved.author.id == self.user.id:
                        embed = message.reference.resolved.embeds[0]
                        content = "<event=player, {}>@{} {}".format(embed.fields[2].value, embed.description, content)
                        # create coroutine to avoid blocking
                        self.loop.create_task(self.player_message_relay(str(message.author.id), content))
                    else:
                        await message.channel.send(f"<@{message.author.id}> Please reply to my embedded message that contains the player name you want to mention instead.", delete_after=5, mention_author=True)
                        return
                else:
                    # create coroutine to avoid blocking
                    self.loop.create_task(self.player_message_relay(str(message.author.id), content))
            else:
                await message.delete()
                await message.channel.send(f"Sorry <@{message.author.id}> ~ Eimi only delivers message for my beloved subscribers ･ﾟ･(｡>ω<｡)･ﾟ･", delete_after=5, mention_author=True)
        elif str(message.channel) in GUILD_CHANNELS:
            await message.delete()
            # TODO
    
    async def setup_hook(self) -> None:
        # setup coroutine before on_ready(), however all coroutine tasks will wait_until_ready() to start
        self.loop.create_task(self.server_message_relay())
        for channel in GUILD_CHANNELS:
            self.loop.create_task(self.guild_message_relay(channel))

    async def player_message_relay(self, user_id, message) -> None:
        # convert unicode to kok emoji if exists
        for uid, kok_id in UNICODE_EMOJI.items():
            message = message.replace(uid, kok_id)

        token = await self.verify_token(user_id)
        url = WSS_URI.replace('{}', token)
        async with websockets.connect(url) as ws:
            await ws.recv()
            await ws.send('40')
            await ws.recv()
            await ws.send(f"42[\"public message\", \"{message}\"]")

    async def server_message_relay(self) -> None:
        # wait self.on_ready()
        await self.wait_until_ready()
        if not self.sync_guild:
            # Nutaku™ King of Kinks EN Community discord
            self.guild = self.get_guild(int(GUILD))
            self.logger.info(f"{self.user.name} is connected to {self.guild}")
            # serves on world-chat channel
            self.public_channel = self.get_channel(int(PUBLIC_CHANNEL))
            self.logger.info(f"{self.user.name} is serving on {self.public_channel}")
            self.sync_guild=True

        while not self.is_closed():
            token = await self.verify_token('0', force_update=True)
            uri = WSS_URI.replace('{}', token)
            try:
                async with websockets.connect(uri) as ws:
                    r = await ws.recv()
                    self.logger.info(f"ws:recv: {r}")
                    await ws.send('40')
                    self.logger.info("ws:send: 40")
                    #await ws.recv()
                    #await ws.send('42["public message", "Hello World from discord.gg/king-of-kinks"]')
                    while not self.is_closed():
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

    async def guild_message_relay(self, channel) -> None:
        # wait self.on_ready()
        await self.wait_until_ready()
        # TODO

    def _get_discord_file(self, icon_name):
        for fname in os.listdir(ALBUMS):
            if fname == icon_name:
                full_path = ALBUMS.joinpath(fname)
                file = discord.File(full_path, icon_name)
                return file
        return None
    
    async def write_message(self, response: str, channel=None):
        # remove 42 from string, load the array into json
        array = json.loads(response[2:])
        match array[0]:
            # public channel
            case "receive message":
                sender = array[1]['sender']
                player_icon = "herocard_{}.jpg".format(sender['icon'][:4])
                create_time = datetime.fromtimestamp(array[1]['msg_time']).astimezone(SERVER_TZ).strftime('%H:%M:%S')
                message = array[1]['message']
                self.logger.info(f"ws:world: {message}")
                # remove in-game attribute, escape characters
                message = message.replace('<event=player, ', '<').replace('\"', '*')
                # replace in-game emojis with discord emojis
                for kok_id, discord_id in KOK_EMOJI.items():
                    message = message.replace(kok_id, discord_id)

                # create embedded message
                if await self.subscriber_list.contains(USER.uuid == sender['user_id']):
                    colour = discord.Colour.yellow()
                else:
                    colour = discord.Colour.blue()
                embedded = discord.Embed(title="[KOK+{}] {}".format(int(sender['server']) - 100, sender['username']), description=sender['username'], colour=colour)
                embedded.set_thumbnail(url=f"attachment://{player_icon}")
                embedded.add_field(name="Level", value=sender['lv'], inline=True)
                embedded.add_field(name="VIP", value=sender['vip_level'], inline=True)
                embedded.add_field(name="UUID", value=sender['user_id'], inline=False)
                embedded.add_field(name="Public Message", value=message, inline=False)
                embedded.set_footer(text=f"message sent at {create_time} EDT")
                file = self._get_discord_file(player_icon)
                await self.public_channel.send(file=file, embed=embedded)
            # guild channel 
            case 'receive guild message':
                sender = array[1]['sender']
                player_icon = "herocard_{}.jpg".format(sender['icon'][:4])
                create_time = datetime.fromtimestamp(array[1]['msg_time']).astimezone(SERVER_TZ).strftime('%H:%M:%S')
                message = array[1]['message']
                self.logger.info(f"ws:world: {message}")
                # remove in-game attribute, escape characters
                message = message.replace('<event=player, ', '<').replace('\"', '*')
                # replace in-game emojis with discord emojis
                for kok_id, discord_id in KOK_EMOJI.items():
                    message = message.replace(kok_id, discord_id)

                # create embedded message
                if await self.subscriber_list.contains(USER.uuid == sender['user_id']):
                    colour = discord.Colour.yellow()
                else:
                    colour = discord.Colour.blue()
                embedded = discord.Embed(title="[KOK+{}] {}".format(int(sender['server']) - 100, sender['username']), description=sender['username'], colour=colour)
                embedded.set_thumbnail(url=f"attachment://{player_icon}")
                embedded.add_field(name="Level", value=sender['lv'], inline=True)
                embedded.add_field(name="VIP", value=sender['vip_level'], inline=True)
                embedded.add_field(name="UUID", value=sender['user_id'], inline=False)
                embedded.add_field(name="Guild Message", value=message, inline=False)
                embedded.set_footer(text=f"message sent at {create_time} EDT")
                file = self._get_discord_file(player_icon)
                await channel.send(file=file, embed=embedded)

            case 'capture country':
                return
            case _:
                return

    async def verify_token(self, user_id, force_update=False) -> str:
        user_data = await self.subscriber_list.get(USER.user_id == user_id)

        if datetime.now().timestamp() - user_data['create_time'] > 21600 or force_update:
            self.logger.info(f"updating (User: {user_id}) token...")
            account = 'https://ntk-login-api.kokmm.net/api/auth/login/game_account'
            account_p = { "login_id": user_data['nutaku_id'], "login_type": 0, "access_token": "", "pw": user_data['nutaku_id']}
            async with aiohttp.ClientSession() as session:
                async with session.post(account, data=account_p) as resp:
                    resp_body = await resp.json()
                    login_info = resp_body['response']
                account_id = login_info['account_id']
                session_id = login_info['session_id']
                login = "https://ntk-login-api.kokmm.net/api/auth/login/user?nutaku_id={}".format(user_data['nutaku_id'])
                login_p = { "server_prefix": user_data['uuid'][:3], "account_id": account_id, "session_id": session_id }
                async with session.post(login, data=login_p) as resp:
                    resp_body = await resp.json()
                    new_token = resp_body['response']['socket_token']
                    new_ts = datetime.now().timestamp()

            await self.subscriber_list.update({ 'token': str(new_token), 'create_time': int(new_ts) }, USER.user_id == user_id)
            self.logger.info(f"(User: {user_id}) token has been updated.")
            return str(new_token)
        else:
            return user_data['token']


if __name__ == '__main__':
    with suppress(KeyboardInterrupt):
        LibrarianSaint().run(SECRET)

