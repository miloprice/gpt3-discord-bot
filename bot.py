# bot.py
import os

import discord
from dotenv import load_dotenv

import openai
load_dotenv()

# Based on https://realpython.com/how-to-make-a-discord-bot-python/

MAX_DEPTH = 64
MAX_BEST_OF = 3

CMD_ARCHIVE = {'!archive'}
CMD_CONTINUE = {'!continue', '!c'}
CMD_HELP = {'!help', '!h'}
CMD_INSTRUCT = {'!instruct', '!i'}
CMD_REROLL = {'!reroll', '!r'}
# One-word unadorned commands for ease of use
PLAIN_COMMANDS = {'continue', 'reroll', 'archive'}

# Braille space, used for EOM to get around discord EOL stripping
MESSAGE_END = "\u2800"
# It's 2000, but need to make space for the EOM char
DISCORD_MSG_LIMIT = 1998

BOT_NAME = '@SmarterAdult'

TOKEN = os.getenv('DISCORD_TOKEN')
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPEN_API_KEY

def get_args_from_content(content):
    arglist = set()
    content = detag_content(content).strip()
    msg_words = content.split()
    for word in msg_words:
        if word.startswith('!'):
            arglist.add(word.lower())
    if content.lower() in PLAIN_COMMANDS:
        arglist.add(f"!{content.lower()}")
    return arglist

def get_args_from_message(message):
    return get_args_from_content(message.clean_content)

def get_best_of_count(message, message_args):
    best_of = 1
    for n in range(2, MAX_BEST_OF+1):
        if f"!{n}" in message_args:
            best_of = n
    return best_of

def detag_content(content):
    return content.replace(f"{BOT_NAME} ", '').strip()

def decommand_content(content, message_args):
    for arg in message_args:
        content = content.replace(arg, '')
    return content

def clean_text(message, message_args, is_archive=False):
    content = detag_content(message.clean_content)
    content = decommand_content(content, message_args)
    content = content.replace(MESSAGE_END, '')
    content = content.strip()
    # cleaned_text = decommand_text(detag_text(message), message_args)
    # Bold text if a human wrote it (kind of hacky)
    if is_archive and message.author != client.user:
        content = ' **' + content + '**'
    return content

def invalid_continue(message, message_args):
    return message.reference is None and message_args.intersection(CMD_CONTINUE)

def invalid_reroll(message, message_args):
    return message.reference is None and message_args.intersection(CMD_REROLL)

# TODO: room for metaprogramming on these
def should_continue(message, message_args):
    return message.reference is not None and message_args.intersection(CMD_CONTINUE)

def should_reroll(message, message_args):
    return message.reference is not None and message_args.intersection(CMD_REROLL)

def should_archive(message, message_args):
    return message.reference is not None and message_args.intersection(CMD_ARCHIVE)

def should_instruct(message, message_args):
    return message_args.intersection(CMD_INSTRUCT)

def should_help(message, message_args):
    return message_args.intersection(CMD_HELP)

def help_text():
    return f"""
How to use this bot

Tag {BOT_NAME} in a message or reply to one of its messages. Writing text prompts the bot to continue the text.

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
    message_args = get_args_from_message(message)

    if should_instruct(message, message_args):
        # !instruct
        global bot_engine
        bot_engine = 'curie-instruct-beta'

    if message.reference is None:
        # Remove leading space for human messages (this should always be a human message)
        return clean_text(message, message_args, is_archive).strip
    elif (depth >= MAX_DEPTH and not is_archive):
        return clean_text(message, message_args, is_archive)
    # TODO: probably doesn't have to be a special case
    elif message.reference and should_continue(message, message_args):
        parent_message = await get_message(message.channel, message.reference.message_id)

        return await get_thread_text(parent_message, depth, is_archive)
    elif message.reference and should_reroll(message, message_args):
        parent_message = await get_message(message.channel, message.reference.message_id)

        # TODO: handle better
        if not parent_message.reference:
            raise "Cannot reroll"

        grandparent_message = await get_message(message.channel, parent_message.reference.message_id)

        return await get_thread_text(grandparent_message, depth, is_archive)
    else:
        # Message is an ancestor
        parent_message = await get_message(message.channel, message.reference.message_id)
        parent_message_args = get_args_from_message(parent_message)

        while should_continue(parent_message, parent_message_args):
            # The message is a user telling the bot to continue; get its ancestors instead until it reaches a bot message
            parent_id = parent_message.reference.message_id
            parent_message = await get_message(message.channel, parent_id)
            parent_message_args = get_args_from_message(parent_message)

        return await get_thread_text(parent_message, depth + 1, is_archive) + clean_text(message, message_args, is_archive)

# Creates an archived version of all messages leading up to the target message
async def archive_thread(message):
    parent_message = await get_message(message.channel, message.reference.message_id)
    full_text = await get_thread_text(parent_message, 0, True)

    server_channels = message.guild.channels
    archive_channel = next (channel for channel in server_channels if channel.name == 'bot-stories')

    while len(full_text) > DISCORD_MSG_LIMIT:
        await archive_channel.send(full_text[:DISCORD_MSG_LIMIT-1])
        full_text = full_text[DISCORD_MSG_LIMIT-1:]

    await archive_channel.send(full_text)
    await message.reply("Story archived in #bot-stories")

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

    message_args = get_args_from_message(message)
    # Handle commands
    if should_help(message, message_args):
        # !help
        await message.reply(help_text())
        return
    elif invalid_continue(message, message_args) or invalid_reroll(message, message_args):
        # Help confused users
        await message.reply(f"You need to reply to a message to do that! Use `{BOT_NAME} !help` for help.")
        return
    elif should_archive(message, message_args):
        # !archive
        await archive_thread(message)
        return

    # TODO: hacky; good argument for stateful Message objects
    global bot_engine
    if should_instruct(message, message_args):
        # !instruct
        bot_engine = 'curie-instruct-beta'
    else:
        bot_engine = 'curie'

    # TODO: probably getting to the point where each message should be a stateful object
    content = await get_thread_text(message)

    # Log content
    print(f"content ({bot_engine}):")
    print(content)

    best_of = get_best_of_count(message, message_args)
    print(f"best of {best_of}")
    completion = openai.Completion.create(engine=bot_engine, prompt=content, max_tokens = 64, best_of = best_of)

    # Log response
    print("response:")
    print(completion.choices)

    response = completion.choices[0].text

    await message.reply(MESSAGE_END + response + MESSAGE_END)


client.run(TOKEN)
