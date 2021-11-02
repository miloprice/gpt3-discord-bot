# bot.py
import os

import discord
import random
from dotenv import load_dotenv

import openai
load_dotenv()

MAX_DEPTH = 8

TOKEN = os.getenv('DISCORD_TOKEN')
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPEN_API_KEY
engines = openai.Engine.list()

message_queue = []

# Based on https://realpython.com/how-to-make-a-discord-bot-python/

def clean_text(message):
    return message.clean_content.replace('@SmarterAdult ', '').strip()

def invalid_continue(message):
    return message.reference is None and clean_text(message).lower() in ['continue', 'go on']

def invalid_reroll(message):
    return message.reference is None and clean_text(message).lower() in ['reroll', 'try again']

def should_continue(message):
    return message.reference is not None and clean_text(message).lower() in ['continue', 'go on']

def should_reroll(message):
    return message.reference is not None and clean_text(message).lower() in ['reroll', 'try again']

def should_archive(message):
    return message.reference is not None and clean_text(message).lower() == 'archive'

# TODO: should have graceful handling for the message not being found
async def get_thread_text(message, depth=0):
    if message.reference is None or depth >= MAX_DEPTH:
        return clean_text(message)
    # TODO: probably doesn't have to be a special case
    elif message.reference and should_continue(message):
        parent_id = message.reference.message_id
        parent_message = await message.channel.fetch_message(parent_id)

        return await get_thread_text(parent_message)
    elif message.reference and should_reroll(message):
        parent_id = message.reference.message_id
        parent_message = await message.channel.fetch_message(parent_id)

        # TODO: handle better
        if not parent_message.reference:
            raise "Cannot reroll"

        grandparent_id = parent_message.reference.message_id
        grandparent_message = await message.channel.fetch_message(grandparent_id)

        return await get_thread_text(grandparent_message)
    else:
        parent_id = message.reference.message_id
        parent_message = await message.channel.fetch_message(parent_id)

        while should_continue(parent_message):
            # The message is a user telling the bot to continue; get its parent instead
            parent_id = parent_message.reference.message_id
            parent_message = await message.channel.fetch_message(parent_id)

        return await get_thread_text(parent_message, depth + 1) + ' ' + clean_text(message)


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
    # Don't respond to self
    if message.author == client.user:
        return
    # Don't respond unless mentioned
    if client.user not in message.mentions:
        return

    # Help confused users
    if invalid_continue(message) or invalid_reroll(message):
        await message.reply("You need to reply to a message to do that!")
        return
    elif should_archive(message):
        parent_id = message.reference.message_id
        parent_message = await message.channel.fetch_message(parent_id)
        full_text = await get_thread_text(parent_message)

        server_channels = message.guild.channels
        archive_channel = next (channel for channel in server_channels if channel.name == 'bot-stories')

        await archive_channel.send(full_text)
        await message.reply("Story archived in #bot-stories")
        return


    content = await get_thread_text(message)

    print("content:")
    print(content)


    completion = openai.Completion.create(engine="davinci", prompt=content, max_tokens = 64)

    print("response:")
    print(completion.choices)

    response = completion.choices[0].text

    await message.reply(response)


client.run(TOKEN)
