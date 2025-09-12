import requests
import json
import google.generativeai as genai
from datetime import datetime
from config.settings import GEMINI_API_KEY

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    gemini_model = None

def get_meme():
    """Get a random meme from API"""
    try:
        response = requests.get('https://meme-api.com/gimme')
        json_data = json.loads(response.text)
        return json_data['url']
    except Exception as e:
        print(f"Error getting meme: {e}")
        return "Sorry, couldn't fetch a meme right now!"

def search_topic(topic):
    """Search for information about a topic using Gemini AI and Wikipedia"""
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

def get_current_date_info():
    """Get formatted current date information"""
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
    
    return response_text

async def get_user_from_mention(guild, user_mention):
    """Get user from mention with improved parsing"""
    if not user_mention.startswith('<@') or not user_mention.endswith('>'):
        return None
    
    try:
        # Handle both <@123456789> and <@!123456789> formats
        user_id = int(user_mention[2:-1].replace('!', ''))
        
        # First try to get from guild cache
        user = guild.get_member(user_id)
        if user:
            return user
        
        # If not found in cache, try to fetch from Discord API
        try:
            user = await guild.fetch_member(user_id)
            return user
        except:
            return None
            
    except ValueError:
        return None
