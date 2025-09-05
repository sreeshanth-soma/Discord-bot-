from typing import Final
import discord
import os
import requests
from dotenv import load_dotenv
import json
import google.generativeai as genai
from datetime import datetime

load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY: Final[str] = os.getenv('GEMINI_API_KEY')

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    gemini_model = None

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

async def process_command(message, is_private=False):
    """Process a command and send response to channel or DM based on is_private flag."""
    content = message.content.lower()
    
    # Search commands
    if content.startswith('--'):
        topic = content[2:].strip()
        
        # Handle date-related queries with real-time information
        if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
            current_date = datetime.now()
            formatted_date = current_date.strftime("%A, %B %d, %Y")
            day_of_year = current_date.timetuple().tm_yday
            days_remaining = 365 - day_of_year if not current_date.year % 4 == 0 else 366 - day_of_year
            
            response_text = f"**Today's Date: {formatted_date}**\n\n"
            response_text += f"📅 **Day of Year:** {day_of_year}\n"
            response_text += f"📅 **Days Remaining:** {days_remaining}\n"
            response_text += f"📅 **Weekday:** {current_date.strftime('%A')}\n"
            response_text += f"📅 **Month:** {current_date.strftime('%B')}\n"
            response_text += f"📅 **Year:** {current_date.year}"
            
            if is_private:
                await message.author.send(response_text)
            else:
                await message.channel.send(response_text)
            return True

        # Search for information about the topic
        result = search_topic(topic)
        if result:
            response_text = f"**{result['title']}**\n{result['extract']}"
            if result.get('url'):
                response_text += f"\n\n🔗 [Learn more]({result['url']})"
        else:
            response_text = "Sorry, I couldn't find information about that topic. Try something more specific like '--python' or '--discord'."
        
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
    
    # Fun commands
    elif content.startswith('hello'):
        response_text = 'Hello World!'
        if is_private:
            response_text += ' (Private)'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('$hello'):
        response_text = 'Hello World!'
        if is_private:
            response_text += ' (Private)'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('$meme') or content == 'meme':
        if is_private:
            await message.author.send(get_meme())
        else:
            await message.channel.send(get_meme())
        return True
        
    elif content.startswith('game?'):
        response_text = 'whatsapp come'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('mic'):
        response_text = 'hey mike, mic on chey ra'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content == 'myid':
        response_text = f"Your Discord User ID: `{message.author.id}`"
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
    
    return False

# Gemini-powered search function
def search_topic(topic):
    try:
        # Handle very generic terms
        generic_terms = ['what', 'who', 'where', 'when', 'why', 'how', 'the', 'a', 'an']
        if topic.lower() in generic_terms:
            return None
        
        # Try Gemini API first (best quality responses)
        if gemini_model:
            try:
                prompt = f"""Provide a concise, informative summary about "{topic}". 
                Include key facts and important details. 
                Keep it under 300 words and make it engaging and educational.
                Format your response as: Title: [Title] | Summary: [Summary]"""
                
                response = gemini_model.generate_content(prompt)
                if response and response.text:
                    # Parse the response
                    text = response.text.strip()
                    if "Title:" in text and "Summary:" in text:
                        parts = text.split("|")
                        title_part = parts[0].replace("Title:", "").strip()
                        summary_part = parts[1].replace("Summary:", "").strip()
                        
                        # Limit summary to 1500 characters to stay under Discord's 2000 limit
                        if len(summary_part) > 1500:
                            summary_part = summary_part[:1500] + "..."
                        
                        return {
                            'title': title_part,
                            'extract': summary_part,
                            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
                        }
                    else:
                        # If format is different, use the whole response but limit length
                        if len(text) > 1500:
                            text = text[:1500] + "..."
                        return {
                            'title': topic.title(),
                            'extract': text,
                            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
                        }
            except Exception as e:
                print(f"Gemini API error: {e}")
        
        # Fallback to Wikipedia API if Gemini fails
        try:
            import urllib.parse
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            encoded_topic = urllib.parse.quote(topic.replace(' ', '_'))
            wiki_response = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}", headers=headers)
            if wiki_response.status_code == 200:
                wiki_data = wiki_response.json()
                if wiki_data.get('extract') and len(wiki_data['extract']) > 50 and not wiki_data['extract'].startswith('may refer to'):
                    return {
                        'title': wiki_data.get('title', topic.title()),
                        'extract': wiki_data['extract'],
                        'url': wiki_data.get('content_urls', {}).get('desktop', {}).get('page', '')
                    }
        except Exception:
            pass
        
        # Final fallback
        return {
            'title': topic.title(),
            'extract': f"I couldn't find detailed information about '{topic.title()}'. Please try a more specific search term or check if the topic name is spelled correctly.",
            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
        }
                
    except Exception as e:
        print(f"Error searching for topic: {e}")
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

    # Process search commands
    if content.startswith('--'):
        await process_command(message, is_private=False)
        return
        
    # Process private commands
    if message.content.startswith('?'):
        # Extract the command after the '?' and process it privately
        private_command = message.content[1:].strip()  # Remove the '?' and get the command
        
        # Handle private search commands
        if private_command.startswith('--'):
            topic = private_command[2:].strip()
            
            # Handle date-related queries with real-time information
            if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
                current_date = datetime.now()
                formatted_date = current_date.strftime("%A, %B %d, %Y")
                day_of_year = current_date.timetuple().tm_yday
                days_remaining = 365 - day_of_year if not current_date.year % 4 == 0 else 366 - day_of_year
                
                response_text = f"**Today's Date: {formatted_date}**\n\n"
                response_text += f"📅 **Day of Year:** {day_of_year}\n"
                response_text += f"📅 **Days Remaining:** {days_remaining}\n"
                response_text += f"📅 **Weekday:** {current_date.strftime('%A')}\n"
                response_text += f"📅 **Month:** {current_date.strftime('%B')}\n"
                response_text += f"📅 **Year:** {current_date.year}"
                
                await message.author.send(response_text)
                return

            # Search for information about the topic
            result = search_topic(topic)
            if result:
                response_text = f"**{result['title']}**\n{result['extract']}"
                if result.get('url'):
                    response_text += f"\n\n🔗 [Learn more]({result['url']})"
                await message.author.send(response_text)
            else:
                await message.author.send("Sorry, I couldn't find information about that topic. Try something more specific like '--python' or '--discord'.")
            return
            
        # Handle other private commands
        elif private_command == 'meme' or private_command == '$meme':
            await message.author.send(get_meme())
            return
        elif private_command == 'myid':
            await message.author.send(f"Your Discord User ID: `{message.author.id}`")
            return
        elif private_command == 'hello':
            await message.author.send('Hello World! (Private)')
            return
        elif private_command == '$hello':
            await message.author.send('Hello World! (Private)')
            return
        elif private_command == 'game?':
            await message.author.send('whatsapp come')
            return
        elif private_command == 'mic':
            await message.author.send('hey mike, mic on chey ra')
            return
        else:
            # Default private response for unknown commands
            await message.author.send('This is a private message response to your question.')
        return
    
    # Help command
    if message.content.startswith('/help') or message.content.startswith('!help'):
        help_text = """
🤖 **Bot Commands Help**

**🔍 Search Commands:**
`--topic` - Search for information about any topic (e.g., `--python`, `--discord`)

**📅 Date & Time:**
`--what is todays date` - Get current date and time information

**👤 User Commands:**
`!myid` - Get your Discord User ID
`!getid @user` - Get another user's ID (admin only)

**💬 Direct Messages:**
`!dm @user message` - Send DM to a server member (admin only)
`!dmid 123456789 message` - Send DM to any user by ID (admin only)

**🎉 Fun Commands:**
`hello` - Say hello
`$hello` - Alternative hello
`$meme` - Get a random meme
`game?` - Gaming invitation
`mic` - Microphone check

**🎭 Entertainment:**
`ep`, `pp`, `bkl`, `lode`, `lawde`, `gandu` - Fun responses

**❓ Private Commands (DM to you):**
`?--topic` - Private search (e.g., `?--python`)
`?meme` - Get a private meme
`?myid` - Get your ID privately
`?hello` - Private hello message
`?game?` - Private gaming invitation
`?mic` - Private mic check
`?` - Default private message

*Use any command to get started!* 🚀
        """
        await message.channel.send(help_text)
        return
    
    # Command to get your user ID
    if message.content.startswith('!myid'):
        await process_command(message, is_private=False)
        return
    
    # Command to get someone's user ID: !getid @user
    if message.content.startswith('!getid'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 1)
                if len(parts) >= 2:
                    user_mention = parts[1]
                    if user_mention.startswith('<@') and user_mention.endswith('>'):
                        user_id = int(user_mention[2:-1])
                        user = message.guild.get_member(user_id)
                        if user:
                            await message.channel.send(f"User ID for {user.display_name}: `{user_id}`")
                        else:
                            await message.channel.send("❌ User not found in this server")
                    else:
                        await message.channel.send("❌ Please mention a user with @username")
                else:
                    await message.channel.send("❌ Usage: !getid @user")
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    
    # Command to send DM to any user by ID: !dmid 123456789 message
    if message.content.startswith('!dmid'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 2)
                if len(parts) >= 3:
                    user_id_str = parts[1]
                    dm_message = parts[2]
                    
                    # Check if it's a valid user ID (numbers only)
                    if user_id_str.isdigit():
                        user_id = int(user_id_str)
                        try:
                            # Get user by ID (works for any Discord user)
                            user = await client.fetch_user(user_id)
                            await user.send(f"Message from {message.author.display_name}: {dm_message}")
                            await message.channel.send(f"✅ DM sent to {user.display_name} (ID: {user_id})")
                        except discord.NotFound:
                            await message.channel.send("❌ User not found with that ID")
                        except discord.Forbidden:
                            await message.channel.send("❌ Cannot send DM to this user (they may have DMs disabled)")
                        except Exception as e:
                            await message.channel.send(f"❌ Error: {str(e)}")
                    else:
                        await message.channel.send("❌ Please provide a valid User ID (numbers only)")
                else:
                    await message.channel.send("❌ Usage: !dmid 123456789012345678 your message here")
            except Exception as e:
                await message.channel.send(f"❌ Error sending DM: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    
    # Command to send DM to a server member: !dm @user message
    if message.content.startswith('!dm'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 2)
                if len(parts) >= 3:
                    user_mention = parts[1]
                    dm_message = parts[2]
                    
                    # Check if it's a user mention (@username)
                    if user_mention.startswith('<@') and user_mention.endswith('>'):
                        user_id = int(user_mention[2:-1])
                        
                        # Try multiple methods to find the user
                        user = message.guild.get_member(user_id)
                        if not user:
                            # Try fetching the user directly
                            try:
                                user = await client.fetch_user(user_id)
                            except:
                                user = None
                        
                        # Debug info
                        await message.channel.send(f"🔍 Debug: Looking for user ID {user_id} in server")
                        await message.channel.send(f"🔍 Debug: Found user: {user}")
                        await message.channel.send(f"🔍 Debug: Server members count: {len(message.guild.members)}")
                        
                        if user:
                            try:
                                await user.send(f"Message from {message.author.display_name}: {dm_message}")
                                await message.channel.send(f"✅ DM sent to {user.display_name}")
                            except discord.Forbidden:
                                await message.channel.send("❌ Cannot send DM to this user (they may have DMs disabled)")
                            except Exception as e:
                                await message.channel.send(f"❌ Error sending DM: {str(e)}")
                        else:
                            await message.channel.send("❌ User not found in this server")
                    else:
                        await message.channel.send("❌ Please mention a user with @username")
                else:
                    await message.channel.send("❌ Usage: !dm @user your message here")
            except Exception as e:
                await message.channel.send(f"❌ Error sending DM: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    # Process fun commands
    if (message.content.startswith('hello') or 
        message.content.startswith('$hello') or 
        message.content.startswith('$meme') or 
        message.content.startswith('game?') or 
        message.content.startswith('mic')):
        await process_command(message, is_private=False)
        return
    
    # Process entertainment commands
    if (message.content.startswith('ep') or 
        message.content.startswith('pp') or 
        message.content.startswith('bkl') or 
        message.content.startswith('lode') or 
        message.content.startswith('lawde') or 
        message.content.startswith('gandu')):
        entertainment_responses = {
            'ep': 'nuvvu ra ep',
            'pp': 'nuvvu pp',
            'bkl': 'em matladuthunav ra maidapindi',
            'lode': 'tuh lode',
            'lawde': 'tuh bk-lawde',
            'gandu': 'tuh gandu dalla'
        }
        for cmd, response in entertainment_responses.items():
            if message.content.startswith(cmd):
                await message.channel.send(response)
                return

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(token=TOKEN)