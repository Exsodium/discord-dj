from dotenv import load_dotenv
from os import getenv
from discord import Intents, Interaction, app_commands, FFmpegOpusAudio
from discord.ext import commands
import logging
from yt_dlp import YoutubeDL
from asyncio import get_running_loop

load_dotenv()
TOKEN = getenv('TOKEN')
YDL_OPTIONS = {
    'format': 'bestaudio[abr<=96]/bestaudio',
    'noplaylist': True,
    'youtube_include_dash_manifest': False,
    'youtube_include_hls_manifest': False,
}
FFMPEG_OPTIONS = ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -c:a libopus -b:a 96k',
}
logger = logging.getLogger(__name__)


async def search_ytdlp_async(query, ydl_opts):
    loop = get_running_loop()
    return await loop.run_in_executor(None, lambda: extract(query, ydl_opts))


def extract(query, ydl_opts):
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding='utf-8',
        filename='app.log',
    )

    intents = Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix='.', intents=intents)

    @bot.event
    async def on_ready() -> None:
        await bot.tree.sync()
        logger.info(f'{bot.user} is online!')

    @bot.tree.command(name='play', description='Включить трек/добавить трек в очередь')
    @app_commands.describe(song_query='Название трека/ссылка на трек')
    async def play(interaction: Interaction, song_query: str) -> None:
        await interaction.response.defer()

        if interaction.user.voice is None:
            await interaction.followup.send('Вы не находитесь в голосовом канале!')
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        else:
            await voice_client.move_to(voice_channel)

        query = f'ytsearch1:{song_query}'
        results = await search_ytdlp_async(query, YDL_OPTIONS)
        tracks = results.get('entries', [])

        if tracks is None:
            await interaction.followup.send('Треки не найдены!')
            return

        track = tracks[0]
        url = track['url']
        title = track.get('title', 'Без названия')
        source = FFmpegOpusAudio(
            url, **FFMPEG_OPTIONS, executable=r'ffmpeg/ffmpeg.exe')
        voice_client.play(source)

    bot.run(TOKEN)


if __name__ == '__main__':
    main()
