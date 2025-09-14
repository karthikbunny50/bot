import logging
import os
import hashlib
import time
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "url_shortener.db")

# ================= LOGGING =================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================= DATABASE FUNCTIONS =================
def init_db():
    """Initialize the database and create tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create URLs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id TEXT UNIQUE NOT NULL,
        original_url TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        click_count INTEGER DEFAULT 0,
        user_id INTEGER,
        user_name TEXT
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def store_url_mapping(unique_id, original_url, user_id, user_name):
    """Store a URL mapping in the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO urls (unique_id, original_url, user_id, user_name) VALUES (?, ?, ?, ?)",
            (unique_id, original_url, user_id, user_name)
        )
        conn.commit()
        logger.info(f"Stored URL mapping: {unique_id} -> {original_url}")
    except sqlite3.IntegrityError:
        logger.error(f"Duplicate unique_id: {unique_id}")
    finally:
        conn.close()

def get_original_url(unique_id):
    """Retrieve the original URL for a given unique ID and increment click count"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get the URL
    cursor.execute(
        "SELECT original_url FROM urls WHERE unique_id = ?",
        (unique_id,)
    )
    result = cursor.fetchone()
    
    if result:
        # Increment click count
        cursor.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE unique_id = ?",
            (unique_id,)
        )
        conn.commit()
        original_url = result[0]
    else:
        original_url = None
    
    conn.close()
    return original_url

def get_stats():
    """Get statistics about URL usage"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM urls")
    total_urls = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(click_count) FROM urls")
    total_clicks = cursor.fetchone()[0] or 0
    
    cursor.execute(
        "SELECT original_url, click_count FROM urls ORDER BY click_count DESC LIMIT 5"
    )
    top_urls = cursor.fetchall()
    
    conn.close()
    
    return {
        "total_urls": total_urls,
        "total_clicks": total_clicks,
        "top_urls": top_urls
    }

# ================= HELPER FUNCTIONS =================
def generate_unique_id(url: str) -> str:
    """Generate a unique identifier for the URL"""
    # Create a hash of the URL + timestamp to ensure uniqueness
    unique_string = f"{url}_{time.time()}"
    return hashlib.md5(unique_string.encode()).hexdigest()

# ================= COMMAND HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command with parameters."""
    user = update.effective_user
    
    # Check if the command has parameters (like a unique ID)
    if context.args:
        unique_id = context.args[0]
        
        # Get the original URL from the database
        original_url = get_original_url(unique_id)
        
        if original_url:
            # Create a button to open the URL
            keyboard = [[InlineKeyboardButton("🌐 Open URL", url=original_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send the URL to the user
            await update.message.reply_text(
                f"🔗 Here's your requested link:\n\n{original_url}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
            # Log the access
            logger.info(f"User {user.id} accessed URL via deep link: {original_url}")
        else:
            await update.message.reply_text(
                "❌ This link is no longer valid or has expired.",
                parse_mode="Markdown"
            )
        return
    
    # If no parameters, send the welcome message
    welcome_message = (
        f"👋 Hello {user.first_name}!\n\n"
        "I'm a URL sharing bot. "
        "Only the admin can generate shareable Telegram links.\n\n"
        "🔗 *How to use:*\n"
        "1. Click on a link shared by the admin\n"
        "2. You'll be directed to the URL\n\n"
        "Contact the admin if you need to share a URL."
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the command /help is issued."""
    help_message = (
        "🤖 *URL Sharing Bot Help*\n\n"
        "I generate Telegram deep links for URLs.\n\n"
        "🔗 *How to use:*\n"
        "• Only the admin can generate links\n"
        "• Click on links shared by the admin\n"
        "• You'll be directed to the URL\n\n"
        "📋 *Supported URLs:*\n"
        "• Website links\n"
        "• YouTube videos\n"
        "• Social media posts\n"
        "• Any valid URL\n\n"
        "🛠 *Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/stats - Show statistics (admin only)"
    )
    
    await update.message.reply_text(help_message, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics about URL usage (admin only)."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 *Admin only command.*", parse_mode="Markdown")
        return
    
    stats = get_stats()
    
    stats_message = (
        f"📊 *URL Statistics*\n\n"
        f"• Total URLs shortened: {stats['total_urls']}\n"
        f"• Total clicks: {stats['total_clicks']}\n\n"
        f"🔝 *Top 5 Most Clicked URLs:*\n"
    )
    
    for i, (url, clicks) in enumerate(stats['top_urls'], 1):
        stats_message += f"{i}. {clicks} clicks - {url[:50]}...\n"
    
    await update.message.reply_text(stats_message, parse_mode="Markdown")

# ================= URL HANDLER =================
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming URLs and generate Telegram deep links."""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text(
            "🚫 *Only the admin can generate links.*",
            parse_mode="Markdown"
        )
        return
    
    message_text = update.message.text
    
    # Basic URL validation
    if not message_text.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ Please send a valid URL starting with http:// or https://",
            parse_mode="Markdown"
        )
        return
    
    # Generate a unique ID for this URL
    unique_id = generate_unique_id(message_text)
    
    # Store the mapping in the database
    store_url_mapping(
        unique_id, 
        message_text, 
        user.id, 
        f"{user.first_name} {user.last_name or ''} (@{user.username or 'N/A'})"
    )
    
    # Get the bot's username
    bot_username = context.bot.username
    
    # Create the Telegram deep link
    deep_link = f"https://t.me/{bot_username}?start={unique_id}"
    
    # Create share buttons
    keyboard = [
        [
            InlineKeyboardButton("🔗 Open URL", url=message_text),
            InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={deep_link}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send the deep link to the user
    result_message = (
        f"✅ *Telegram Deep Link Generated*\n\n"
        f"🔗 *Your URL:*\n`{message_text}`\n\n"
        f"➡️ *Telegram Deep Link:*\n`{deep_link}`\n\n"
        f"📤 *Share this link with your users!*"
    )
    
    await update.message.reply_text(result_message, parse_mode="Markdown", reply_markup=reply_markup)
    
    # Log the action
    logger.info(f"Admin {user.id} generated deep link for URL: {message_text} -> {deep_link}")

# ================= BUTTON HANDLER =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("copy_"):
        url = query.data[5:]  # Remove "copy_" prefix
        await query.edit_message_text(
            f"📋 *URL Copied to Clipboard*\n\n"
            f"🔗 *URL:*\n`{url}`\n\n"
            f"📤 You can now paste this URL anywhere!",
            parse_mode="Markdown"
        )

# ================= ERROR HANDLER =================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Exception while handling an update: {context.error}")

# ================= MAIN =================
def main():
    """Start the bot."""
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN not set in environment variables")
    
    # Initialize the database
    init_db()
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("URL Sharing Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()