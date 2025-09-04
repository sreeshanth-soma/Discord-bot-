from typing import Final
import discord
import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

# wikipedia
def search_wikipedia(topic):
    try:
        response = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}")
        response.raise_for_status()  
        data = response.json()
        return data
    except Exception as e:
        print(f"Error searching Wikipedia: {e}")
        return None
    
class MyClient(discord.Client):
  async def on_ready(self):
    print('Logged on as {0}!'.format(self.user))

  async def on_member_join(self, member):
          channel = member.guild.system_channel  # Get the system channel of the guild (default welcome channel)
          if channel is not None:
              await channel.send(f'{member.display_name} has joined the server!')

  async def on_message(self, message):
    if message.author == self.user:
      return
    
    content = message.content.lower()  # Convert message content to lowercase for case-insensitive matching

    if content.startswith('--'):
        # Extract the topic from the message content
        topic = content[2:].strip()

        # Search Wikipedia for the topic
        result = search_wikipedia(topic)
        if result:
            # Send information about the topic to the channel
            await message.channel.send(f"**{result['title']}**\n{result['extract']}")
        else:
            await message.channel.send("Sorry, I couldn't find information about that topic.")
        
    if message.content.startswith('?'):
        await message.author.send('This is a private message response to your question.')
        return
    if message.content.startswith('hello'):
        await message.channel.send('Hello World!')
    if message.content.startswith('$hello'):
        await message.channel.send('Hello World!')
    if message.content.startswith('ep'):
        await message.channel.send('nuvvu ra ep')
    if message.content.startswith('pp'):
        await message.channel.send('nuvvu pp')
    if message.content.startswith('bkl'):
        await message.channel.send('em matladuthunav ra maidapindi')
    if message.content.startswith('lode'):
        await message.channel.send('tuh lode')
    if message.content.startswith('lawde'):
        await message.channel.send('tuh bk-lawde')
    if message.content.startswith('gandu'):
        await message.channel.send('tuh gandu dalla')
    if message.content.startswith('$meme'):
      await message.channel.send(get_meme())
    if message.content.startswith('game?'):
       await message.channel.send('whatsapp come')
    if message.content.startswith('mic'):
       await message.channel.send('hey mike, mic on chey ra')

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(token=TOKEN)
from typing import Final
import discord
import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

# wikipedia
def search_wikipedia(topic):
    try:
        response = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}")
        response.raise_for_status()  
        data = response.json()
        return data
    except Exception as e:
        print(f"Error searching Wikipedia: {e}")
        return None
    
class MyClient(discord.Client):
  async def on_ready(self):
    print('Logged on as {0}!'.format(self.user))

  async def on_member_join(self, member):
          channel = member.guild.system_channel  # Get the system channel of the guild (default welcome channel)
          if channel is not None:
              await channel.send(f'{member.display_name} has joined the server!')

  async def on_message(self, message):
    if message.author == self.user:
      return
    
    content = message.content.lower()  # Convert message content to lowercase for case-insensitive matching

    if content.startswith('--'):
        # Extract the topic from the message content
        topic = content[2:].strip()

        # Search Wikipedia for the topic
        result = search_wikipedia(topic)
        if result:
            # Send information about the topic to the channel
            await message.channel.send(f"**{result['title']}**\n{result['extract']}")
        else:
            await message.channel.send("Sorry, I couldn't find information about that topic.")
        
    if message.content.startswith('?'):
        await message.author.send('This is a private message response to your question.')
        return
    if message.content.startswith('hello'):
        await message.channel.send('Hello World!')
    if message.content.startswith('$hello'):
        await message.channel.send('Hello World!')
    if message.content.startswith('$meme'):
      await message.channel.send(get_meme())
    if message.content.startswith('game?'):
       await message.channel.send('whatsapp come')
    if message.content.startswith('mic'):
       await message.channel.send('hey mike, mic on chey ra')

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(token=TOKEN)