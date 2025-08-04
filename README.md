# YouTube Telegram Bot 🎬

A powerful Telegram bot that allows users to download YouTube videos in various formats and qualities directly through Telegram chat.

## Features ✨

- **Easy to Use**: Simply paste a YouTube URL and get download options
- **Multiple Quality Options**: High (720p), Medium (480p), and Low quality downloads
- **Format Support**: Download as MP4 video or MP3 audio
- **Video Information**: Shows title, channel, duration, and view count before download
- **File Size Management**: Automatically handles Telegram's 50MB file limit
- **Clean Interface**: Interactive buttons for selecting download options
- **Auto Cleanup**: Removes downloaded files after sending to save storage

## Quality Options 📊

| Quality | Resolution | Best For |
|---------|------------|----------|
| High | Up to 720p | Desktop viewing, good internet |
| Medium | Up to 480p | Mobile viewing, moderate internet |
| Low | Lowest available | Slow internet, minimal data usage |

## Format Options 🎵🎬

- **MP4**: Full video with audio (various qualities)
- **MP3**: Audio-only extraction (192 kbps quality)

## Prerequisites 📋

- Python 3.7+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- FFmpeg (for audio conversion)

## Installation 🚀

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd youtube-telegram-bot
   ```

2. **Install required packages**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg**
   
   **Ubuntu/Debian:**
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```
   
   **macOS:**
   ```bash
   brew install ffmpeg
   ```
   
   **Windows:**
   Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

4. **Set up environment variables**
   ```bash
   export BOT_TOKEN="your_telegram_bot_token_here"
   ```
   
   Or create a `.env` file:
   ```
   BOT_TOKEN=your_telegram_bot_token_here
   ```

## Required Dependencies 📦

Create a `requirements.txt` file with:

```txt
python-telegram-bot==20.7
yt-dlp==2023.12.30
asyncio
```

## Getting a Bot Token 🔑

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the provided token
5. Set it as your `BOT_TOKEN` environment variable

## Usage 💡

1. **Start the bot**
   ```bash
   python bot.py
   ```

2. **In Telegram:**
   - Send `/start` to see the welcome message
   - Send `/help` for detailed instructions
   - Paste any YouTube URL to begin downloading

3. **Download Process:**
   - Bot validates the YouTube URL
   - Displays video information (title, duration, views)
   - Shows download options with interactive buttons
   - Downloads and sends the file to you
   - Automatically cleans up temporary files

## Commands 🎮

- `/start` - Welcome message and bot introduction
- `/help` - Detailed help and usage instructions

## File Structure 📁

```
youtube-telegram-bot/
├── bot.py              # Main bot script
├── requirements.txt    # Python dependencies
├── downloads/          # Temporary download folder (auto-created)
├── README.md          # This file
└── .env               # Environment variables (create this)
```

## Configuration ⚙️

The bot creates a `downloads/` folder automatically for temporary file storage. Files are deleted after successful upload to save disk space.

### Customizable Settings

You can modify these settings in the `YouTubeDownloader` class:

- `download_path`: Change temporary download location
- Quality formats: Modify resolution limits in `download_video()` method
- Audio quality: Change MP3 bitrate (default: 192 kbps)

## Limitations ⚠️

- **File Size**: Maximum 50MB per file (Telegram bot limitation)
- **Supported Sites**: Currently YouTube only (easily extensible)
- **Concurrent Downloads**: One download per user at a time
- **Storage**: Files are temporary and deleted after upload

## Error Handling 🛠️

The bot handles various error scenarios:

- Invalid YouTube URLs
- Video unavailable or private
- Download failures
- File size too large
- Network connectivity issues

## Development 👨‍💻

### Adding New Features

1. **Support for other platforms**: Modify `is_valid_youtube_url()` method
2. **Custom quality settings**: Extend the quality options in button callbacks
3. **User preferences**: Add database integration for user settings
4. **Download history**: Implement logging for downloaded videos

### Code Structure

- `YouTubeDownloader`: Handles all download operations
- `start()`, `help_command()`: Command handlers
- `handle_url()`: Processes YouTube URLs and shows options
- `button_callback()`: Handles download button presses
- `handle_text()`: Routes text messages appropriately

## Deployment 🌐

### Local Development
```bash
python bot.py
```

### Production Deployment

1. **Using systemd (Linux):**
   ```bash
   sudo nano /etc/systemd/system/youtube-bot.service
   ```
   
   Add service configuration and enable:
   ```bash
   sudo systemctl enable youtube-bot
   sudo systemctl start youtube-bot
   ```

2. **Using Docker:**
   ```dockerfile
   FROM python:3.9-slim
   RUN apt-get update && apt-get install -y ffmpeg
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .
   CMD ["python", "bot.py"]
   ```

3. **Cloud Platforms:**
   - Heroku: Add `Procfile` with `worker: python bot.py`
   - Railway, Render: Configure start command as `python bot.py`

## Troubleshooting 🔍

**Common Issues:**

1. **"Module not found" error**
   ```bash
   pip install -r requirements.txt
   ```

2. **FFmpeg not found**
   - Install FFmpeg for your operating system
   - Ensure it's in your system PATH

3. **Bot not responding**
   - Check bot token is correct
   - Verify internet connection
   - Check bot permissions in Telegram

4. **Download fails**
   - Video might be private or unavailable
   - Try different quality option
   - Check if video is region-restricted

## Contributing 🤝

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License 📄

This project is licensed under the MIT License. See LICENSE file for details.

## Disclaimer ⚖️

This bot is for educational purposes. Users are responsible for complying with YouTube's Terms of Service and respecting copyright laws. Only download content you have permission to download.

## Support 💬

If you encounter issues or have suggestions:
- Open an issue on GitHub
- Check existing issues for solutions
- Contribute improvements via pull requests

---

**Made with ❤️ for the Telegram community**
