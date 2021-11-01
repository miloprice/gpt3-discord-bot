# bot.py
import os

import discord
import random
from dotenv import load_dotenv

import openai
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPEN_API_KEY
engines = openai.Engine.list()


# Based on https://realpython.com/how-to-make-a-discord-bot-python/

client = discord.Client()

@client.event
async def on_ready():
    print("Ready")

@client.event
async def on_member_join(member):
    await member.create_dm()
    await member.dm_channel.send(
        f'Hi {member.name}, welcome to my Discord server!'
    )

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user not in message.mentions:
        return
    # if message.channel.name != 'where-is-milo':
    #     return

    content = message.clean_content
    content = content.replace('@SmarterAdult ', '')
    print("content:")
    print(content)

    content = message.author.name + 'said to me, a very amusing comedian, ' + content + '. I replied:'

    completion = openai.Completion.create(engine="davinci", prompt=content, max_tokens = 32)

    print(completion.choices)

    response = completion.choices[0].text

    await message.channel.send(response)


client.run(TOKEN)
