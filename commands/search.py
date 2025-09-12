from utils.helpers import search_topic, get_current_date_info

async def handle_search_command(message, is_private=False):
    """Handle search commands that start with --"""
    content = message.content.lower()
    
    if content.startswith('--'):
        topic = content[2:].strip()
        
        # Handle date-related queries with real-time information
        if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
            response_text = get_current_date_info()
            
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
    
    return False

async def handle_private_search_command(message):
    """Handle private search commands that start with ?--"""
    if message.content.startswith('?'):
        private_command = message.content[1:].strip()
        
        if private_command.startswith('--'):
            topic = private_command[2:].strip()
            
            # Handle date-related queries
            if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
                response_text = get_current_date_info()
                await message.author.send(response_text)
                return True

            # Search for information about the topic
            result = search_topic(topic)
            if result:
                response_text = f"**{result['title']}**\n{result['extract']}"
                if result.get('url'):
                    response_text += f"\n\n🔗 [Learn more]({result['url']})"
                await message.author.send(response_text)
            else:
                await message.author.send("Sorry, I couldn't find information about that topic. Try something more specific like '--python' or '--discord'.")
            return True
    
    return False
