# Importing libraries and modules
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp
from collections import deque
import asyncio

# Environment variables for tokens and other sensitive data
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Create the structure for queuing songs - Dictionary of queues
SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)
    except Exception as e:
        print(f"Error extracting info from YouTube: {e}")
        return None

# Setup of intents. Intents are permissions the bot has on the server
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Bot ready-up code
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.command(name="skip", description="Skips the current playing song")
async def skip(ctx):
    if ctx.guild.voice_client and (ctx.guild.voice_client.is_playing() or ctx.guild.voice_client.is_paused()):
        ctx.guild.voice_client.stop()
        await ctx.send("Skipped the current song.")
    else:
        await ctx.send("Not playing anything to skip.")

@bot.command(name="pause", description="Pause the currently playing song.")
async def pause(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client is None:
        return await ctx.send("I'm not in a voice channel.")
    if not voice_client.is_playing():
        return await ctx.send("Nothing is currently playing.")
    voice_client.pause()
    await ctx.send("Playback paused!")

@bot.command(name="resume", description="Resume the currently paused song.")
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client is None:
        return await ctx.send("I'm not in a voice channel.")
    if not voice_client.is_paused():
        return await ctx.send("I’m not paused right now.")
    voice_client.resume()
    await ctx.send("Playback resumed!")

@bot.command(name="stop", description="Stop playback and clear the queue.")
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return await ctx.send("I'm not connected to any voice channel.")
    guild_id_str = str(ctx.guild.id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    await voice_client.disconnect()
    await ctx.send("Stopped playback and disconnected!")

@bot.command(name="play", description="Play a song or add it to the queue.")
async def play(ctx, *, song_query: str):
    # Check if the user is in a voice channel
    voice_channel = ctx.author.voice.channel
    if voice_channel is None:
        await ctx.send("You must be in a voice channel.")
        return

    # Connect to the voice channel
    voice_client = ctx.guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    # Search for the song using yt-dlp
    ydl_options = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    }

    query = "ytsearch1: " + song_query
    results = await search_ytdlp_async(query, ydl_options)

    # Handle empty or invalid results
    if not results or "entries" not in results or not results["entries"]:
        await ctx.send("No results found for your query.")
        return

    tracks = results["entries"]
    first_track = tracks[0]
    audio_url = first_track.get("url")
    title = first_track.get("title", "Untitled")

    if not audio_url:
        await ctx.send("Could not retrieve the audio URL for this track.")
        return

    # Add the song to the queue
    guild_id = str(ctx.guild.id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    # Play the song or add it to the queue
    if voice_client.is_playing() or voice_client.is_paused():
        await ctx.send(f"Added to queue: **{title}**")
    else:
        await ctx.send(f"Now playing: **{title}**")
        await play_next_song(voice_client, guild_id, ctx.channel)

async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
        }

        try:
            source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)
            def after_play(error):
                if error:
                    print(f"Error playing {title}: {error}")
                asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

            voice_client.play(source, after=after_play)
            asyncio.create_task(channel.send(f"Now playing: **{title}**"))
        except Exception as e:
            print(f"Error playing audio: {e}")
            await channel.send("An error occurred while trying to play the song.")
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()

# Run the bot
bot.run(TOKEN)