import discord
from discord.ext import commands
from discord import app_commands

from yt_dlp import YoutubeDL
from asyncio import run_coroutine_threadsafe


class Options:
    YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': 'True', 'impersonate': ''}
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}


class Song:
    nowplaying = ""
    nowplaying_source = None


class MusicClient:
    voice_client = None
    voice_channel = None

    # 2d array containing [song, channel]
    music_queue = []

    is_playing = False
    is_paused = False
    is_looped = False


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ? searching the item on youtube

    def search_yt(self, item):
        with YoutubeDL(Options.YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info("ytsearch:%s" %
                                        item, download=False)['entries'][0]
            except Exception:
                return False
        return {'source': info['url'], 'title': info['title']}

    def play_music(self):
        if len(MusicClient.music_queue) > 0:
            MusicClient.is_playing = True

            # ! remove the first element as you are currently playing it
            Song.nowplaying = MusicClient.music_queue[0][0]['title']
            Song.nowplaying_source = MusicClient.music_queue[0][0]['source']
            MusicClient.voice_channel = MusicClient.music_queue[0][1]
            MusicClient.music_queue.pop(0)

            MusicClient.voice_client.play(discord.FFmpegPCMAudio(
                Song.nowplaying_source, **Options.FFMPEG_OPTIONS), after=lambda e: self.song_finished())
            MusicClient.voice_client.pause()
            MusicClient.voice_client.resume()
        else:
            MusicClient.is_playing = False

    def song_finished(self):
        if len(MusicClient.voice_channel.members) < 2 or (not MusicClient.is_looped and len(MusicClient.music_queue) == 0):
            MusicClient.is_playing = False
            MusicClient.is_paused = False
            run_coroutine_threadsafe(
                MusicClient.voice_client.disconnect(), self.bot.loop)
        elif MusicClient.is_looped:
            MusicClient.voice_client.play(discord.FFmpegPCMAudio(
                Song.nowplaying_source, **Options.FFMPEG_OPTIONS), after=lambda e: self.song_finished())
        else:  # len(MusicClient.music_queue) > 0
            self.play_music()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Loaded music.py!')

    @app_commands.command(name="play", description="Plays a selected song from youtube")
    @app_commands.guild_only()
    @app_commands.describe(song="What to play")
    async def play(self, interaction: discord.Interaction, song: str):
        user_voice = interaction.user.voice
        if user_voice is None:
            # ! you need to be connected so that the bot knows where to go
            await self.bot.embed(interaction, "Connect to the voice channel", ephemeral=True)
        else:
            await interaction.response.defer()
            youtube_strings = [
                "https://www.youtube.com/watch?v=", "https://youtu.be/"]
            for i in youtube_strings:
                if song.startswith(i):
                    song.replace(i, '')

            song = self.search_yt(song)
            if type(song) == type(True):
                await self.bot.embed(interaction, "Could not download the song. Incorrect format try another keyword. This could be due to playlist or a livestream format", followup=True)
            else:
                MusicClient.music_queue.append([song, user_voice.channel])

                if MusicClient.voice_client is None or not MusicClient.voice_client.is_connected():
                    MusicClient.voice_client = await MusicClient.music_queue[0][1].connect()

                if MusicClient.is_playing is False:
                    self.play_music()

                await self.bot.embed(interaction, title="Added song to the queue:", description=song['title'], followup=True)

    @app_commands.command(name="pause_resume", description="Pauses the current song being played")
    @app_commands.guild_only()
    async def pause_resume(self, interaction: discord.Interaction):
        if MusicClient.is_playing:
            MusicClient.is_playing = False
            MusicClient.is_paused = True
            MusicClient.voice_client.pause()
            await self.bot.embed(interaction, "Pause on")
        elif MusicClient.is_paused:
            MusicClient.is_paused = False
            MusicClient.is_playing = True
            MusicClient.voice_client.resume()
            await self.bot.embed(interaction, "Pause off")

    @app_commands.command(name="skip", description="Skips the current song being played")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        if MusicClient.voice_client is not None and MusicClient.voice_client.is_connected() and len(MusicClient.music_queue) > 0:
            MusicClient.voice_client.pause()
            self.play_music()
            await self.bot.embed(interaction, title="Song skipped", description=f"Nowplaying: {Song.nowplaying}")
        else:
            await self.bot.embed(interaction, "No music in queue")

    @app_commands.command(name="queue", description="Displays the queue")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        retval = ""
        for i in range(0, len(MusicClient.music_queue)):
            # ? display a max of 5 songs in the current queue
            if (i > 4):
                break
            retval += MusicClient.music_queue[i][0]['title'] + "\n"

        if retval != "":
            await self.bot.embed(interaction, retval, title="Queue:")
        else:
            await self.bot.embed(interaction, "No music in queue")

    @app_commands.command(name="queue_clear", description="Stops the music and clears the queue")
    @app_commands.guild_only()
    async def queue_clear(self, interaction: discord.Interaction):
        if MusicClient.voice_client is not None and MusicClient.is_playing:
            MusicClient.voice_client.stop()
        MusicClient.music_queue = []
        await self.bot.embed(interaction, "Music queue cleared")

    @app_commands.command(name="leave", description="Kick the bot from voice chat")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        MusicClient.is_playing = False
        MusicClient.is_paused = False
        MusicClient.music_queue = []
        await MusicClient.voice_client.disconnect()
        await self.bot.embed(interaction, "Bot left the voice chat")

    @app_commands.command(name="nowplaying", description="Prints the current song name")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction):
        if interaction.user.voice is None or MusicClient.is_playing is False:
            await self.bot.embed(interaction, "No song is playing")

        await self.bot.embed(interaction, Song.nowplaying, title="Now Playing:")

    @app_commands.command(name="loop", description="Loops the song")
    @app_commands.guild_only()
    async def loop(self, interaction: discord.Interaction):
        user_voice = interaction.user.voice
        if user_voice is None:
            # ! you need to be connected so that the bot knows where to go
            await self.bot.embed(interaction, "Connect to the voice channel", ephemeral=True)
        else:
            MusicClient.is_looped ^= True
            if MusicClient.is_looped is False:
                await self.bot.embed(interaction, "Loop is now off")
            else:
                await self.bot.embed(interaction, "Loop is now on")


async def setup(bot):
    await bot.add_cog(Music(bot))
