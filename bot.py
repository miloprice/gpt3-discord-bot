# bot.py
import os

import discord
import random
from dotenv import load_dotenv

import openai
load_dotenv()

# Based on https://realpython.com/how-to-make-a-discord-bot-python/

MAX_DEPTH = 20

CMD_ARCHIVE = '!archive'
CMD_CONTINUE = '!continue'
CMD_HELP = '!help'
CMD_INSTRUCT = '!instruct'
CMD_REROLL = '!reroll'

TOKEN = os.getenv('DISCORD_TOKEN')
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPEN_API_KEY
engines = openai.Engine.list()

# TODO: hacky; find a cleaner approach
def detag_text(message):
    return message.clean_content.replace('@SmarterAdult ', '').strip()

def decommand_text(text):
    return text.replace(CMD_INSTRUCT, '').replace(CMD_INSTRUCT.upper(), '').replace(CMD_INSTRUCT[:2], '').replace(CMD_INSTRUCT[:2].upper(), '').strip()

def clean_text(message, is_archive=False):
    cleaned_text = decommand_text(detag_text(message))
    # Bold text if a human wrote it (kind of hacky)
    if is_archive and message.author != client.user:
        cleaned_text = '**' + cleaned_text + '**'
    return cleaned_text

def invalid_continue(message):
    return message.reference is None and clean_text(message).lower() in ['continue', 'go on', CMD_CONTINUE, CMD_CONTINUE[:2]]

def invalid_reroll(message):
    return message.reference is None and clean_text(message).lower() in ['reroll', CMD_REROLL, CMD_REROLL[:2]]

def should_continue(message):
    return message.reference is not None and clean_text(message).lower() in ['continue', 'go on', CMD_CONTINUE, CMD_CONTINUE[:2]]

def should_reroll(message):
    return message.reference is not None and clean_text(message).lower() in ['reroll', CMD_REROLL, CMD_REROLL[:2]]

def should_archive(message):
    return message.reference is not None and clean_text(message).lower() in ['archive', CMD_ARCHIVE, CMD_ARCHIVE[:2]]

def should_instruct(message):
    return detag_text(message).lower().startswith(CMD_INSTRUCT[:2])

def should_help(message):
    return detag_text(message).lower().startswith(CMD_HELP[:2])

def help_text():
    return """
How to use this bot

Tag @SmarterAdult in a message or reply to one of its messages. Writing text prompts the bot to continue the text.

There are some special commands as well:
!archive (!a) - (in reply to a message) tells the bot to save the whole story, ending at the message, in the channel #bot-stories (if it exists).
!continue (!c) - (in reply to a message) tells the bot to continue writing from the message
!help (!h) - shows this message
!instruct (!i) - sets the bot to "instruct" mode. Example: `!i Tell a story about a cabbage` will generate a story about a cabbage without you needing to write the first part.
!reroll (!r) - (in reply to a message) comes up with a new message based on the message's parent.
"""

async def get_message(channel, target_id):
    cache_message = discord.utils.get(client.cached_messages, id=target_id)
    if cache_message:
        print(f"Found message in cache: {target_id}")
        return cache_message
    else:
        return await channel.fetch_message(target_id)


# TODO: should have graceful handling for the message not being found
async def get_thread_text(message, depth=0, is_archive=False):
    if should_instruct(message):
        # !instruct
        global bot_engine
        bot_engine = 'curie-instruct-beta'

    if message.reference is None or (depth >= MAX_DEPTH and not is_archive):
        return clean_text(message, is_archive)
    # TODO: probably doesn't have to be a special case
    elif message.reference and should_continue(message):
        parent_message = await get_message(message.channel, message.reference.message_id)

        return await get_thread_text(parent_message, depth, is_archive)
    elif message.reference and should_reroll(message):
        parent_message = await get_message(message.channel, message.reference.message_id)

        # TODO: handle better
        if not parent_message.reference:
            raise "Cannot reroll"

        grandparent_message = await get_message(message.channel, parent_message.reference.message_id)

        return await get_thread_text(grandparent_message, depth, is_archive)
    else:
        # Message is an ancestor
        parent_message = await get_message(message.channel, message.reference.message_id)

        while should_continue(parent_message):
            # The message is a user telling the bot to continue; get its ancestors instead until it reaches a bot message
            parent_id = parent_message.reference.message_id
            parent_message = await get_message(message.channel, parent_id)

        # TODO: find a way to allow non-space-joined messages
        return await get_thread_text(parent_message, depth + 1, is_archive) + ' ' + clean_text(message, is_archive)

client = discord.Client()

@client.event
async def on_ready():
    print("Ready")

@client.event
async def on_message(message):
    # Don't respond to self
    if message.author == client.user:
        return
    # Don't respond unless mentioned
    if client.user not in message.mentions:
        return

    # Handle commands
    if should_help(message):
        # !help
        await message.reply(help_text())
        return
    elif invalid_continue(message) or invalid_reroll(message):
        # Help confused users
        await message.reply("You need to reply to a message to do that! Use `@SmarterAdult !help` for help.")
        return
    elif should_archive(message):
        # !archive
        parent_message = await get_message(message.channel, message.reference.message_id)
        full_text = await get_thread_text(parent_message, 0, True)

        server_channels = message.guild.channels
        archive_channel = next (channel for channel in server_channels if channel.name == 'bot-stories')

        while len(full_text) > 2000:
            await archive_channel.send(full_text[:1999])
            full_text = full_text[1999:]

        await archive_channel.send(full_text)
        await message.reply("Story archived in #bot-stories")
        return

    global bot_engine
    if should_instruct(message):
        # !instruct
        bot_engine = 'curie-instruct-beta'
    else:
        bot_engine = 'curie'

    content = await get_thread_text(message)

    if len(content) == 0:
        await message.reply("THE END")
        return

    # Log content
    print(f"content ({bot_engine}):")
    print(content)

    completion = openai.Completion.create(engine=bot_engine, prompt=content, max_tokens = 64)

    # Log response
    print("response:")
    print(completion.choices)

    response = completion.choices[0].text

    await message.reply(response)


client.run(TOKEN)
