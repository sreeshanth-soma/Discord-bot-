import requests
import google.genai as genai

# -----------------------------
# 1. Get latest news headlines
# -----------------------------
NEWS_API_KEY = "175334f23b244b9d96cc6a6fc7ec6968"  # your NewsAPI key
url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"

response = requests.get(url)
news_data = response.json()

# Extract top 5 headlines
headlines = [article["title"] for article in news_data["articles"][:5]]
news_text = "\n".join(headlines)

print("Latest Headlines:")
print(news_text)

# -----------------------------
# 2. Send to Gemini Flash Lite
# -----------------------------
GEMINI_API_KEY='AIzaSyAsfgn7GWI8yx8ZN6NJCrU1hWmtQapUgAE' # replace with your Gemini API key
client = genai.Client(api_key=GEMINI_API_KEY)

prompt = f"""
Here are some latest news headlines:

{news_text}

Who is the president of the US?

Please give me a short, clear summary (3–4 bullet points).
"""
sed

result = client.models.generate_content(
    model="models/gemini-2.5-flash-lite",
    contents=prompt
)

print("\nGemini Summary:")
print(result.text)
