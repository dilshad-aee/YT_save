import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
import asyncio
from urllib.parse import urlparse
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token - replace with your actual bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")

class YouTubeDownloader:
    def __init__(self):
        self.download_path = "downloads/"
        os.makedirs(self.download_path, exist_ok=True)

    def is_valid_youtube_url(self, url):
        """Check if the URL is a valid YouTube URL"""
        youtube_regex = re.compile(
            r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
            r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        )
        return youtube_regex.match(url) is not None

    async def get_video_info(self, url):
        """Get video information without downloading"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'thumbnail': info.get('thumbnail', None),
                    'formats': info.get('formats', [])
                }
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    async def download_video(self, url, quality='best', format_type='mp4'):
        """Download video with specified quality"""
        try:
            filename = f"{self.download_path}%(title)s.%(ext)s"
            
            if format_type == 'mp3':
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': filename,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                }
            else:
                if quality == 'high':
                    format_selector = 'best[height<=720]'
                elif quality == 'medium':
                    format_selector = 'best[height<=480]'
                elif quality == 'low':
                    format_selector = 'worst'
                else:
                    format_selector = 'best'
                
                ydl_opts = {
                    'format': format_selector,
                    'outtmpl': filename,
                    'quiet': True,
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                
                # Find the downloaded file
                title = info.get('title', 'video')
                ext = 'mp3' if format_type == 'mp3' else info.get('ext', 'mp4')
                
                # Clean filename for filesystem
                safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
                filepath = os.path.join(self.download_path, f"{safe_title}.{ext}")
                
                # Find actual downloaded file (yt-dlp might change the name)
                for file in os.listdir(self.download_path):
                    if safe_title in file and file.endswith(f'.{ext}'):
                        actual_filepath = os.path.join(self.download_path, file)
                        if os.path.exists(actual_filepath):
                            return actual_filepath
                
                return filepath if os.path.exists(filepath) else None
                
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return None

# Initialize downloader
downloader = YouTubeDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
🎬 *YouTube Video Downloader Bot*

Welcome! Send me a YouTube URL and I'll help you download it.

*Commands:*
/start - Show this message
/help - Show help information

*How to use:*
1. Send me any YouTube video URL
2. Choose your preferred quality and format
3. Download and enjoy!

*Supported formats:*
• MP4 (Video)
• MP3 (Audio only)

Just paste a YouTube link to get started! 🚀
    """
    
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """
🆘 *Help - YouTube Downloader Bot*

*How to download:*
1. Copy any YouTube video URL
2. Paste it in this chat
3. Select quality (High/Medium/Low)
4. Choose format (MP4/MP3)
5. Wait for download to complete

*Quality options:*
• High: Up to 720p
• Medium: Up to 480p  
• Low: Lowest available quality

*Format options:*
• MP4: Video with audio
• MP3: Audio only

*Tips:*
• Longer videos take more time
• High quality = larger file size
• MP3 format extracts audio only

Need more help? Just send me a YouTube link! 😊
    """
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube URL messages"""
    url = update.message.text.strip()
    
    if not downloader.is_valid_youtube_url(url):
        await update.message.reply_text(
            "❌ Please send a valid YouTube URL.\n\n"
            "Example: https://www.youtube.com/watch?v=VIDEO_ID"
        )
        return

    # Show loading message
    loading_msg = await update.message.reply_text("🔍 Getting video information...")
    
    # Get video info
    video_info = await downloader.get_video_info(url)
    
    if not video_info:
        await loading_msg.edit_text("❌ Failed to get video information. Please check the URL and try again.")
        return

    # Format duration
    duration = video_info['duration']
    if duration:
        minutes, seconds = divmod(duration, 60)
        duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
    else:
        duration_str = "Unknown"

    # Format view count
    view_count = video_info.get('view_count', 0)
    if view_count:
        if view_count >= 1000000:
            view_str = f"{view_count/1000000:.1f}M views"
        elif view_count >= 1000:
            view_str = f"{view_count/1000:.1f}K views"
        else:
            view_str = f"{view_count} views"
    else:
        view_str = "Unknown views"

    # Create info message
    info_text = f"""
🎬 *Video Information*

📝 *Title:* {video_info['title'][:50]}{'...' if len(video_info['title']) > 50 else ''}
👤 *Channel:* {video_info['uploader']}
⏱️ *Duration:* {duration_str}
👁️ *Views:* {view_str}

Choose your preferred download options:
    """

    # Create inline keyboard for download options
    keyboard = [
        [
            InlineKeyboardButton("🎬 High Quality MP4", callback_data=f"download_high_mp4_{url}"),
            InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"download_best_mp3_{url}")
        ],
        [
            InlineKeyboardButton("📱 Medium Quality MP4", callback_data=f"download_medium_mp4_{url}"),
            InlineKeyboardButton("📺 Low Quality MP4", callback_data=f"download_low_mp4_{url}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_msg.edit_text(
        info_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks for download options"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    data_parts = query.data.split('_', 3)
    if len(data_parts) < 4:
        await query.edit_message_text("❌ Invalid selection.")
        return
    
    action, quality, format_type, url = data_parts
    
    if action != "download":
        return

    # Update message to show download started
    format_name = "MP3 Audio" if format_type == "mp3" else f"{quality.title()} Quality MP4"
    await query.edit_message_text(f"⬇️ Downloading {format_name}...\nPlease wait, this may take a few minutes.")
    
    # Download the video
    filepath = await downloader.download_video(url, quality, format_type)
    
    if not filepath or not os.path.exists(filepath):
        await query.edit_message_text("❌ Download failed. Please try again or choose a different quality.")
        return
    
    # Check file size (Telegram has a 50MB limit for bots)
    file_size = os.path.getsize(filepath)
    if file_size > 50 * 1024 * 1024:  # 50MB
        await query.edit_message_text(
            "❌ File is too large (>50MB) to send via Telegram.\n"
            "Try downloading with lower quality."
        )
        os.remove(filepath)  # Clean up
        return
    
    try:
        # Send the file
        await query.edit_message_text("📤 Uploading file...")
        
        with open(filepath, 'rb') as file:
            if format_type == 'mp3':
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=file,
                    caption="🎵 Downloaded by YouTube Bot"
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file,
                    caption="🎬 Downloaded by YouTube Bot"
                )
        
        await query.edit_message_text("✅ Download completed successfully!")
        
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await query.edit_message_text("❌ Failed to send file. Please try again.")
    
    finally:
        # Clean up downloaded file
        if os.path.exists(filepath):
            os.remove(filepath)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    text = update.message.text
    
    # Check if it's a URL
    if 'youtube.com' in text or 'youtu.be' in text:
        await handle_url(update, context)
    else:
        await update.message.reply_text(
            "🔗 Please send me a YouTube URL to download.\n\n"
            "Example: https://www.youtube.com/watch?v=VIDEO_ID\n\n"
            "Type /help for more information."
        )

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Run the bot
    print("🤖 YouTube Telegram Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
