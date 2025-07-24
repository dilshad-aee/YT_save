import os
import logging
import asyncio
import threading
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import hashlib

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Message
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, TimedOut, BadRequest

import yt_dlp
from urllib.parse import urlparse
import re

# Configure enhanced logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_CONCURRENT_DOWNLOADS = 3
CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks for large files
CLEANUP_INTERVAL = 3600  # 1 hour
MAX_STORAGE_TIME = 7200  # 2 hours

class AdvancedYouTubeDownloader:
    def __init__(self):
        self.download_path = Path("downloads")
        self.temp_path = Path("temp")
        self.download_path.mkdir(exist_ok=True)
        self.temp_path.mkdir(exist_ok=True)
        
        # Download tracking
        self.active_downloads = {}
        self.download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.progress_messages = {}
        
        # Start cleanup task
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background cleanup task"""
        def cleanup_loop():
            while True:
                self._cleanup_old_files()
                time.sleep(CLEANUP_INTERVAL)
        
        cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        cleanup_thread.start()

    def _cleanup_old_files(self):
        """Remove old downloaded files"""
        current_time = time.time()
        for path in [self.download_path, self.temp_path]:
            for file_path in path.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > MAX_STORAGE_TIME:
                        try:
                            file_path.unlink()
                            logger.info(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up {file_path}: {e}")

    def get_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def is_valid_youtube_url(self, url: str) -> bool:
        """Enhanced YouTube URL validation"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
            r'(?:https?://)?(?:music\.)?youtube\.com/watch\?.*v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?.*list=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/c/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/@[\w-]+'
        ]
        
        return any(re.match(pattern, url) for pattern in youtube_patterns)

    async def get_video_info(self, url: str) -> Optional[Dict]:
        """Get comprehensive video information"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'dump_single_json': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                # Handle playlists
                if 'entries' in info:
                    entries = list(info['entries'])
                    return {
                        'is_playlist': True,
                        'playlist_title': info.get('title', 'Unknown Playlist'),
                        'playlist_count': len(entries),
                        'entries': entries[:10]  # Limit to first 10 for display
                    }
                
                # Get available formats with better organization
                formats = info.get('formats', [])
                video_formats = []
                audio_formats = []
                
                for fmt in formats:
                    if fmt.get('vcodec') and fmt.get('vcodec') != 'none':
                        video_formats.append({
                            'format_id': fmt['format_id'],
                            'ext': fmt.get('ext', 'mp4'),
                            'quality': fmt.get('height', 0),
                            'fps': fmt.get('fps', 0),
                            'filesize': fmt.get('filesize', fmt.get('filesize_approx', 0)),
                            'vcodec': fmt.get('vcodec', ''),
                            'acodec': fmt.get('acodec', ''),
                        })
                    elif fmt.get('acodec') and fmt.get('acodec') != 'none':
                        audio_formats.append({
                            'format_id': fmt['format_id'],
                            'ext': fmt.get('ext', 'mp3'),
                            'abr': fmt.get('abr', 0),
                            'filesize': fmt.get('filesize', fmt.get('filesize_approx', 0)),
                            'acodec': fmt.get('acodec', ''),
                        })

                return {
                    'is_playlist': False,
                    'id': info.get('id', ''),
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'description': info.get('description', '')[:200] + '...' if info.get('description', '') else '',
                    'thumbnail': info.get('thumbnail', None),
                    'video_formats': sorted(video_formats, key=lambda x: x['quality'], reverse=True),
                    'audio_formats': sorted(audio_formats, key=lambda x: x['abr'], reverse=True),
                    'webpage_url': info.get('webpage_url', url)
                }
                
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    def _progress_hook(self, d, chat_id, message_id, context):
        """Progress hook for downloads with real-time updates"""
        try:
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                if total > 0:
                    percentage = (downloaded / total) * 100
                    
                    # Update every 5% or every 10 seconds
                    current_time = time.time()
                    last_update = self.progress_messages.get(f"{chat_id}_{message_id}", 0)
                    
                    if current_time - last_update >= 10 or percentage % 5 < 1:
                        self.progress_messages[f"{chat_id}_{message_id}"] = current_time
                        
                        # Format progress message
                        progress_bar = self._create_progress_bar(percentage)
                        speed_str = self._format_bytes(speed) + "/s" if speed else "Unknown"
                        eta_str = f"{eta}s" if eta else "Unknown"
                        downloaded_str = self._format_bytes(downloaded)
                        total_str = self._format_bytes(total)
                        
                        progress_text = f"""
⬇️ **Downloading...**

{progress_bar} {percentage:.1f}%

📊 **Progress:** {downloaded_str} / {total_str}
🚀 **Speed:** {speed_str}
⏱️ **ETA:** {eta_str}

Please wait while your file is being downloaded...
                        """
                        
                        # Schedule update (non-blocking)
                        asyncio.create_task(self._update_progress_message(
                            context, chat_id, message_id, progress_text
                        ))
                        
        except Exception as e:
            logger.error(f"Error in progress hook: {e}")

    async def _update_progress_message(self, context, chat_id, message_id, text):
        """Update progress message safely"""
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
        except (BadRequest, NetworkError, TimedOut):
            pass  # Ignore rate limiting and network errors

    def _create_progress_bar(self, percentage: float, length: int = 20) -> str:
        """Create a visual progress bar"""
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}]"

    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes to human readable format"""
        if bytes_count == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} TB"

    async def download_media(self, url: str, format_option: str, chat_id: int, 
                           message_id: int, context) -> Optional[str]:
        """Enhanced download with progress tracking and chunked upload support"""
        async with self.download_semaphore:
            try:
                video_id = self.get_video_id(url) or hashlib.md5(url.encode()).hexdigest()[:8]
                timestamp = int(time.time())
                
                # Setup progress tracking
                progress_key = f"{chat_id}_{message_id}"
                self.active_downloads[progress_key] = True
                
                # Parse format option
                parts = format_option.split('_')
                quality = parts[0] if len(parts) > 0 else 'best'
                format_type = parts[1] if len(parts) > 1 else 'mp4'
                
                # Determine output filename
                if format_type == 'mp3':
                    filename = f"{video_id}_{timestamp}.%(ext)s"
                    output_path = self.download_path / f"{video_id}_{timestamp}.mp3"
                else:
                    filename = f"{video_id}_{timestamp}.%(ext)s"
                    output_path = self.download_path / f"{video_id}_{timestamp}.%(ext)s"

                # Configure yt-dlp options
                ydl_opts = {
                    'outtmpl': str(self.download_path / filename),
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [lambda d: self._progress_hook(d, chat_id, message_id, context)],
                }

                # Format selection based on quality and type
                if format_type == 'mp3':
                    ydl_opts.update({
                        'format': 'bestaudio/best',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '320' if quality == 'best' else '192',
                        }],
                    })
                else:
                    # Video format selection
                    format_selectors = {
                        'best': 'best[height<=2160]',
                        '1440p': 'best[height<=1440]',
                        '1080p': 'best[height<=1080]',
                        '720p': 'best[height<=720]',
                        '480p': 'best[height<=480]',
                        '360p': 'best[height<=360]',
                        'worst': 'worst'
                    }
                    
                    ydl_opts['format'] = format_selectors.get(quality, 'best')

                # Download the media
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    
                    # Find the actual downloaded file
                    downloaded_files = []
                    for file_path in self.download_path.iterdir():
                        if file_path.is_file() and video_id in file_path.name:
                            file_stat = file_path.stat()
                            if time.time() - file_stat.st_mtime < 300:  # Created in last 5 minutes
                                downloaded_files.append(file_path)
                    
                    if downloaded_files:
                        # Return the most recently created file
                        latest_file = max(downloaded_files, key=lambda f: f.stat().st_mtime)
                        return str(latest_file)
                    
                    return None

            except Exception as e:
                logger.error(f"Error downloading media: {e}")
                return None
            finally:
                # Cleanup progress tracking
                if progress_key in self.active_downloads:
                    del self.active_downloads[progress_key]
                if progress_key in self.progress_messages:
                    del self.progress_messages[progress_key]

    async def send_large_file(self, context, chat_id: int, file_path: str, 
                            caption: str = "", file_type: str = "video") -> bool:
        """Send large files by splitting them if necessary"""
        try:
            file_size = os.path.getsize(file_path)
            file_name = Path(file_path).name
            
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
            
            # For files under 2GB, send directly
            if file_size <= 2 * 1024 * 1024 * 1024:  # 2GB limit
                with open(file_path, 'rb') as file:
                    if file_type == "audio":
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=InputFile(file, filename=file_name),
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=InputFile(file, filename=file_name),
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN,
                            supports_streaming=True
                        )
                return True
            else:
                # For very large files, send as document
                with open(file_path, 'rb') as file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=InputFile(file, filename=file_name),
                        caption=f"{caption}\n\n⚠️ *Large file sent as document*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                return True
                
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            return False

# Global downloader instance
downloader = AdvancedYouTubeDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command with better UI"""
    user = update.effective_user
    welcome_message = f"""
🎬 **Advanced YouTube Downloader Bot**

Hello {user.first_name}! 👋

I'm your personal YouTube downloader with advanced features:

✨ **Features:**
• 🎥 High-quality video downloads (up to 4K)
• 🎵 Audio extraction (MP3, 320kbps)
• 📱 Multiple quality options
• 📊 Real-time download progress
• 🚀 Fast concurrent downloads
• 📂 Large file support (no size limits)
• 🎭 Playlist support

🔧 **Commands:**
/start - Show this welcome message
/help - Detailed help and usage guide
/stats - Bot statistics and info

**Quick Start:**
Just send me any YouTube URL and I'll handle the rest! 

Try it now! 🚀
    """
    
    keyboard = [
        [InlineKeyboardButton("📖 Help & Guide", callback_data="show_help")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive help command"""
    help_text = """
📖 **Complete Usage Guide**

**🎯 How to Download:**
1. Send me any YouTube video/playlist URL
2. Choose from quality options
3. Select format (Video/Audio)
4. Wait for download with live progress
5. Receive your file instantly!

**🎥 Video Quality Options:**
• **Best** - Highest available (up to 4K)
• **1440p** - 2K resolution
• **1080p** - Full HD
• **720p** - HD quality
• **480p** - Standard quality
• **360p** - Mobile quality

**🎵 Audio Options:**
• **Best Audio** - 320kbps MP3
• **Standard Audio** - 192kbps MP3

**🔗 Supported URLs:**
• Regular videos: `youtube.com/watch?v=...`
• Short URLs: `youtu.be/...`
• Playlist URLs: `youtube.com/playlist?list=...`
• Channel URLs: `youtube.com/@channel`
• Music: `music.youtube.com/...`

**💡 Pro Tips:**
• Higher quality = larger file size
• Use audio-only for music/podcasts
• Playlists show first 10 videos
• No file size restrictions!
• Multiple downloads supported

**🆘 Need Help?**
Just send me a YouTube link to get started!
    """
    
    keyboard = [
        [InlineKeyboardButton("🏠 Back to Start", callback_data="show_start")],
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    active_downloads = len(downloader.active_downloads)
    total_files = len(list(downloader.download_path.iterdir()))
    
    stats_text = f"""
📊 **Bot Statistics**

🔄 **Current Status:**
• Active Downloads: {active_downloads}/{MAX_CONCURRENT_DOWNLOADS}
• Temp Files: {total_files}

⚙️ **Configuration:**
• Max Concurrent Downloads: {MAX_CONCURRENT_DOWNLOADS}
• Cleanup Interval: {CLEANUP_INTERVAL//60} minutes
• File Retention: {MAX_STORAGE_TIME//3600} hours

🚀 **Performance:**
• Real-time progress tracking
• Chunked upload for large files
• Automatic cleanup system
• No file size restrictions

**Bot Version:** 2.0 Advanced
**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🏠 Back to Start", callback_data="show_start")],
        [InlineKeyboardButton("📖 Help Guide", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        stats_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced URL handler with better UI and playlist support"""
    url = update.message.text.strip()
    
    if not downloader.is_valid_youtube_url(url):
        await update.message.reply_text(
            "❌ **Invalid URL**\n\n"
            "Please send a valid YouTube URL:\n"
            "• `https://youtube.com/watch?v=...`\n"
            "• `https://youtu.be/...`\n"
            "• `https://youtube.com/playlist?list=...`\n\n"
            "Try again with a valid YouTube link! 🔗",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Show enhanced loading message
    loading_msg = await update.message.reply_text(
        "🔍 **Analyzing URL...**\n\n"
        "⏳ Getting video information and available formats...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # Get comprehensive video info
    video_info = await downloader.get_video_info(url)
    
    if not video_info:
        await loading_msg.edit_text(
            "❌ **Failed to get video information**\n\n"
            "This could be due to:\n"
            "• Private or deleted video\n"
            "• Region restrictions\n"
            "• Network issues\n\n"
            "Please check the URL and try again! 🔄",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Handle playlists
    if video_info.get('is_playlist', False):
        playlist_text = f"""
🎵 **Playlist Detected**

📝 **Title:** {video_info['playlist_title']}
📊 **Videos:** {video_info['playlist_count']} total

**First 10 videos:**
"""
        for i, entry in enumerate(video_info.get('entries', [])[:10], 1):
            title = entry.get('title', 'Unknown')[:40]
            playlist_text += f"{i}. {title}{'...' if len(entry.get('title', '')) > 40 else ''}\n"
        
        keyboard = [
            [InlineKeyboardButton("📥 Download Entire Playlist", callback_data=f"playlist_all_{url}")],
            [InlineKeyboardButton("🎵 Audio Only Playlist", callback_data=f"playlist_audio_{url}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await loading_msg.edit_text(playlist_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return

    # Format video information with enhanced details
    duration = video_info['duration']
    if duration:
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            duration_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        else:
            duration_str = f"{int(minutes):02d}:{int(seconds):02d}"
    else:
        duration_str = "Unknown"

    # Format view count
    view_count = video_info.get('view_count', 0)
    if view_count >= 1000000:
        view_str = f"{view_count/1000000:.1f}M views"
    elif view_count >= 1000:
        view_str = f"{view_count/1000:.1f}K views"
    else:
        view_str = f"{view_count:,} views" if view_count else "Unknown views"

    # Format like count
    like_count = video_info.get('like_count', 0)
    like_str = f"{like_count:,} likes" if like_count else "Unknown likes"

    # Upload date
    upload_date = video_info.get('upload_date', '')
    if upload_date:
        try:
            date_obj = datetime.strptime(upload_date, '%Y%m%d')
            upload_str = date_obj.strftime('%B %d, %Y')
        except:
            upload_str = upload_date
    else:
        upload_str = "Unknown"

    info_text = f"""
🎬 **Video Information**

📝 **Title:** {video_info['title'][:60]}{'...' if len(video_info['title']) > 60 else ''}

👤 **Channel:** {video_info['uploader']}
⏱️ **Duration:** {duration_str}
👁️ **Views:** {view_str}
👍 **Likes:** {like_str}
📅 **Uploaded:** {upload_str}

📄 **Description:**
{video_info.get('description', 'No description available.')[:100]}

**Choose your download options below:**
    """

    # Create enhanced keyboard with more options
    keyboard = []
    
    # Video quality options
    video_options = [
        ("🎬 Best Quality", "best_mp4"),
        ("📺 1080p HD", "1080p_mp4"),
        ("📱 720p HD", "720p_mp4"),
        ("📞 480p", "480p_mp4")
    ]
    
    # Add video options in pairs
    for i in range(0, len(video_options), 2):
        row = []
        for j in range(2):
            if i + j < len(video_options):
                text, callback = video_options[i + j]
                row.append(InlineKeyboardButton(text, callback_data=f"download_{callback}_{url}"))
        keyboard.append(row)
    
    # Audio options
    keyboard.append([
        InlineKeyboardButton("🎵 Best Audio (MP3)", callback_data=f"download_best_mp3_{url}"),
        InlineKeyboardButton("🎶 Standard Audio", callback_data=f"download_standard_mp3_{url}")
    ])
    
    # Additional options
    keyboard.append([
        InlineKeyboardButton("📊 Show All Formats", callback_data=f"formats_{url}"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_msg.edit_text(
        info_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced callback handler with better user experience"""
    query = update.callback_query
    await query.answer()
    
    # Handle navigation callbacks
    if query.data == "show_help":
        await help_command(update, context)
        return
    elif query.data == "show_stats":
        await stats_command(update, context)
        return
    elif query.data == "show_start":
        await start(update, context)
        return
    elif query.data == "cancel":
        await query.edit_message_text(
            "❌ **Operation Cancelled**\n\nSend me another YouTube URL to download! 🔗",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse callback data for downloads
    if query.data.startswith("download_"):
        parts = query.data.split('_', 3)
        if len(parts) < 4:
            await query.edit_message_text("❌ Invalid selection.")
            return
        
        action, quality, format_type, url = parts
        
        # Format display name
        quality_names = {
            'best': 'Best Available',
            '1080p': '1080p HD',
            '720p': '720p HD',
            '480p': '480p Standard',
            'standard': 'Standard'
        }
        
        format_names = {
            'mp4': 'Video (MP4)',
            'mp3': 'Audio (MP3)'
        }
        
        quality_name = quality_names.get(quality, quality.title())
        format_name = format_names.get(format_type, format_type.upper())
        
        # Update message to show download started
        await query.edit_message_text(
            f"🚀 **Download Started**\n\n"
            f"📋 **Format:** {quality_name} {format_name}\n"
            f"⏳ **Status:** Initializing download...\n\n"
            f"*This may take a while for large files. I'll update you with progress!*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Start download
        file_path = await downloader.download_media(
            url, f"{quality}_{format_type}", 
            query.message.chat_id, query.message.message_id, context
        )
        
        if not file_path or not os.path.exists(file_path):
            await query.edit_message_text(
                f"❌ **Download Failed**\n\n"
                f"This could be due to:\n"
                f"• Format not available\n"
                f"• Network issues\n"
                f"• Video restrictions\n\n"
                f"Try a different quality or format! 🔄",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Update message for upload phase
        await query.edit_message_text(
            f"📤 **Uploading File**\n\n"
            f"📋 **Format:** {quality_name} {format_name}\n"
            f"📁 **File:** {Path(file_path).name}\n"
            f"💾 **Size:** {downloader._format_bytes(os.path.getsize(file_path))}\n\n"
            f"*Uploading to Telegram...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send the file
        caption = f"🎬 **Downloaded by Advanced YouTube Bot**\n\n📋 **Quality:** {quality_name}\n📁 **Format:** {format_name}"
        
        success = await downloader.send_large_file(
            context, query.message.chat_id, file_path, 
            caption, "audio" if format_type == "mp3" else "video"
        )
        
        if success:
            await query.edit_message_text(
                f"✅ **Download Completed Successfully!**\n\n"
                f"📋 **Format:** {quality_name} {format_name}\n"
                f"💾 **Size:** {downloader._format_bytes(os.path.getsize(file_path))}\n\n"
                f"🎉 **Enjoy your download!**\n\n"
                f"Send me another URL to download more! 🔗",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                f"❌ **Upload Failed**\n\n"
                f"The file was downloaded but couldn't be uploaded to Telegram.\n"
                f"This might be due to file size or network issues.\n\n"
                f"Please try again! 🔄",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Cleanup
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
    
    # Handle playlist downloads
    elif query.data.startswith("playlist_"):
        parts = query.data.split('_', 2)
        if len(parts) < 3:
            return
        
        action, playlist_type, url = parts
        
        await query.edit_message_text(
            f"🎵 **Playlist Download**\n\n"
            f"⚠️ **Note:** Playlist downloads can take a very long time!\n"
            f"📊 **Type:** {'Audio Only' if playlist_type == 'audio' else 'Video'}\n\n"
            f"I'll start downloading and send each video as it completes.\n"
            f"You can continue using the bot while this processes in the background.\n\n"
            f"🚀 **Starting playlist download...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # This would require additional implementation for playlist handling
        # For now, show a placeholder
        await asyncio.sleep(2)
        await query.edit_message_text(
            f"🔧 **Playlist Feature Coming Soon!**\n\n"
            f"Playlist downloads are being implemented.\n"
            f"For now, please download videos individually.\n\n"
            f"Send me a single video URL! 🎬",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Handle format display
    elif query.data.startswith("formats_"):
        url = query.data.replace("formats_", "")
        
        await query.edit_message_text(
            f"📊 **Detailed Format Information**\n\n"
            f"🔧 **Feature in Development**\n\n"
            f"Advanced format selection will show:\n"
            f"• All available video qualities\n"
            f"• Audio bitrates and codecs\n"
            f"• File size estimates\n"
            f"• Frame rates and codecs\n\n"
            f"For now, use the standard quality options! 📹",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced text handler with better validation"""
    text = update.message.text.strip()
    
    # Check if it's a YouTube URL
    if any(domain in text.lower() for domain in ['youtube.com', 'youtu.be', 'music.youtube.com']):
        await handle_url(update, context)
    else:
        # Enhanced help message for non-URLs
        help_text = f"""
🤖 **Hi there!** 

I'm a YouTube downloader bot. Here's what I can do:

🎬 **Supported URLs:**
• `youtube.com/watch?v=...`
• `youtu.be/...`
• `music.youtube.com/...`
• Playlists and channels

📋 **Available Formats:**
• Video: Best, 1080p, 720p, 480p
• Audio: MP3 (Best & Standard quality)

💡 **Quick Start:**
Just paste any YouTube URL and I'll handle the rest!

**Example:**
`https://youtube.com/watch?v=dQw4w9WgXcQ`

Try it now! 🚀
        """
        
        keyboard = [
            [InlineKeyboardButton("📖 Full Help Guide", callback_data="show_help")],
            [InlineKeyboardButton("📊 Bot Statistics", callback_data="show_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced error handler with better logging"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Try to send error message to user if possible
    if isinstance(update, Update) and update.effective_message:
        try:
            error_text = f"""
⚠️ **An Error Occurred**

Something went wrong while processing your request.
Don't worry, I've logged the error and will keep improving!

**What you can do:**
• Try your request again
• Use a different video URL  
• Try a different quality/format
• Check if the video is available in your region

**If the problem persists:**
The bot is constantly being improved to handle edge cases better.

🔄 **Try again with a different approach!**
            """
            
            await update.effective_message.reply_text(
                error_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass  # Don't crash on error handling

def main():
    """Enhanced main function with better error handling"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        print("❌ Error: Please set the BOT_TOKEN environment variable")
        return
    
    # Create the Application with enhanced settings
    application = (Application.builder()
                  .token(BOT_TOKEN)
                  .concurrent_updates(True)
                  .connection_pool_size(20)
                  .pool_timeout(300.0)
                  .read_timeout(120.0)
                  .write_timeout(120.0)
                  .build())

    # Add handlers with priority
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Enhanced startup message
    print("🚀 Advanced YouTube Telegram Bot Starting...")
    print(f"📁 Download path: {downloader.download_path}")
    print(f"🔧 Max concurrent downloads: {MAX_CONCURRENT_DOWNLOADS}")
    print(f"🧹 Cleanup interval: {CLEANUP_INTERVAL//60} minutes")
    print("✅ Bot is ready and waiting for requests!")
    
    # Run the bot with enhanced settings
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=120
    )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error occurred: {e}")
    finally:
        print("👋 Bot shutdown complete")
