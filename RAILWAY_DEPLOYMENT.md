# Discord Bot - Railway Deployment Guide

## 🚀 Deploy to Railway (Super Easy!)

Railway is perfect for Discord bots - it's free, reliable, and much simpler than Azure.

### **Step 1: Push to GitHub**
```bash
git init
git add .
git commit -m "Discord bot ready for Railway"
git remote add origin https://github.com/yourusername/Discord-bot-.git
git push -u origin main
```

### **Step 2: Deploy on Railway**
1. Go to [railway.app](https://railway.app)
2. Sign up with your GitHub account
3. Click **"New Project"**
4. Select **"Deploy from GitHub repo"**
5. Choose your Discord bot repository
6. Click **"Deploy Now"**

### **Step 3: Add Environment Variables**
In Railway dashboard:
1. Go to your project
2. Click **"Variables"** tab
3. Add these variables:

```
DISCORD_TOKEN=your_discord_token_here
GEMINI_API_KEY=your_gemini_api_key_here
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
```

### **Step 4: Deploy!**
Railway will automatically:
- ✅ Install dependencies from `requirements.txt`
- ✅ Run your bot with `python main_bot.py`
- ✅ Keep it running 24/7
- ✅ Auto-restart if it crashes

## 💰 **Cost & Benefits**

### **Railway Free Tier:**
- ✅ **$5 free credit/month**
- ✅ **500 hours runtime** (enough for 24/7)
- ✅ **Automatic deployments**
- ✅ **Built-in monitoring**
- ✅ **No region restrictions**

### **Why Railway > Azure:**
- ✅ **Much simpler** setup (5 minutes vs 3 hours!)
- ✅ **No container complexity**
- ✅ **Better for Discord bots**
- ✅ **Automatic scaling**
- ✅ **Great free tier**

## 🎯 **Expected Result**
- Your bot will be **online in Discord** within 5 minutes
- **All features working**: music, moderation, fun commands
- **Automatic updates** when you push to GitHub
- **24/7 uptime** with auto-restart

## 📝 **Files Created for Railway:**
- `railway.json` - Railway configuration
- `Procfile` - Tells Railway how to run your bot
- `requirements.txt` - Already exists (Python dependencies)
- `main_bot.py` - Your main bot file (already exists)

**Railway is MUCH easier than Azure - your bot will be online in minutes!** 🎉
