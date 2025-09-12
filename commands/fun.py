import discord
from utils.helpers import get_meme

async def handle_hello(message, is_private=False):
    """Handle hello command"""
    response_text = 'Hello World!'
    if is_private:
        response_text += ' (Private)'
        await message.author.send(response_text)
    else:
        await message.channel.send(response_text)

async def handle_meme(message, is_private=False):
    """Handle meme command"""
    meme_url = get_meme()
    if is_private:
        await message.author.send(meme_url)
    else:
        await message.channel.send(meme_url)

async def handle_game(message, is_private=False):
    """Handle game command"""
    response_text = 'whatsapp come'
    if is_private:
        await message.author.send(response_text)
    else:
        await message.channel.send(response_text)

async def handle_mic(message, is_private=False):
    """Handle mic command"""
    response_text = 'hey mike, mic on chey ra'
    if is_private:
        await message.author.send(response_text)
    else:
        await message.channel.send(response_text)


async def handle_entertainment_commands(message):
    """Handle entertainment commands"""
    content = message.content.lower()
    entertainment_responses = {
        'ep': 'nuvvu ra ep',
        'pp': 'nuvvu pp',
        'bkl': 'em matladuthunav ra maidapindi',
        'lode': 'tuh lode',
        'lawde': 'tuh bk-lawde',
        'gandu': 'tuh gandu dalla'
    }
    
    for cmd, response in entertainment_responses.items():
        if content.startswith(cmd):
            await message.channel.send(response)
            return True
    return False

# Fun command processors
async def process_fun_command(message, is_private=False):
    """Process fun commands"""
    content = message.content.lower()
    
    if content.startswith('hello') or content.startswith('$hello'):
        await handle_hello(message, is_private)
        return True
    elif content.startswith('$meme') or content == 'meme':
        await handle_meme(message, is_private)
        return True
    elif content.startswith('game?'):
        await handle_game(message, is_private)
        return True
    elif content.startswith('mic'):
        await handle_mic(message, is_private)
        return True
    
    return False
