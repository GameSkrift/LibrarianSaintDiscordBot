# Librarian Saint Eimi

[![](https://img.shields.io/discord/565048515357835264.svg?logo=discord&colorB=7289DA&label=discord)](https://discord.gg/eSustM8e5q)
> This bot is not ready to be public yet!

Librarian Saint Eimi is a open source Discord bot coded in Python3 with [discord.py](discordpy.rtfd.org/en/latest)

## Features (TODO)
* Relay chat messages in game world channel on discord.

## Installation

**Python 3.10 or higher is required!**

To install the development version, do the following:
```bash
git clone https://github.com/GameSkrift/LibrarianSaintDiscordBot
cd LibrarianSaintDiscordBot
pip3 install -r requirements.txt
# see the other code snippet 
touch .env
python3 main.py
```
To be mentioned user has to provide own `.env` file in project root directory, with required constant variables:
```python
SECRET = #secret token of discord bot which can be found in Developer Portal.
GUILD = #copy discord server ID
CHANNEL = #copy channel ID
STORAGE = #JSON filepath used by TinyDB
```

## DISCLAIMER

This project is made by players from unofficial community [discord](https://discord.gg/king-of-kinks). We are in no way affiliated with Nutaku Games™, Nutaku Publishing™ or the developers of King of Kinks™.
