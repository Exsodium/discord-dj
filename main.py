from dotenv import load_dotenv
from os import getenv
from discord import Intents, Interaction, app_commands, FFmpegOpusAudio
from discord.ext import commands
import logging
from yt_dlp import YoutubeDL
from asyncio import get_running_loop, run_coroutine_threadsafe, create_task
from collections import deque

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
    queue = deque()

    @bot.event
    async def on_ready() -> None:
        await bot.tree.sync()
        logger.info(f'Бот {bot.user.name} запущен!')

    @bot.tree.command(name='play', description='Включить трек/добавить трек в очередь')
    @app_commands.describe(song_query='Название трека/ссылка на трек')
    async def play_track(interaction: Interaction, song_query: str) -> None:
        await interaction.response.defer()

        if interaction.user.voice is None:
            await interaction.followup.send('**Вы должны быть в голосовом канале!**')
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        else:
            await voice_client.move_to(voice_channel)

        if '&' in song_query:
            song_query = song_query.split('&')[0]

        query = f'ytsearch1:{song_query}'
        results = await search_ytdlp_async(query, YDL_OPTIONS)
        entries = results.get('entries', [])

        if not entries:
            await interaction.followup.send('Трек не найден!')
            return

        track: dict = entries[0]
        url = track['url']
        title = track['title']
        queue.append((url, title))

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f'Добавлено в очередь: **{title}**')
        else:
            await play_next_track(voice_client, interaction.channel)

    async def play_next_track(voice_client, channel) -> None:
        if queue:
            url, title = queue[0]
            source = FFmpegOpusAudio(
                source=url,
                **FFMPEG_OPTIONS,
                executable=r'ffmpeg/ffmpeg.exe'
            )

            def after_play(error):
                queue.popleft()

                if error:
                    print(f'Ошибка воспроизведения {title}: {error}')
                run_coroutine_threadsafe(play_next_track(
                    voice_client, channel), bot.loop)

            voice_client.play(source, after=after_play)
            create_task(channel.send(f'Сейчас играет: **{title}**'))
        else:
            await voice_client.disconnect()

    @bot.tree.command(name='skip', description='Пропустить трек')
    async def skip_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            current_track_title = queue[0][1]
            voice_client.stop()
            await interaction.response.send_message(f'Пропущено: **{current_track_title}**')
        else:
            await interaction.response.send_message('Ничего не играет!')

    @bot.tree.command(name='pause', description='Поставить трек на паузу')
    async def pause_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_playing():
            current_track_title = queue[0][1]
            voice_client.pause()
            await interaction.response.send_message(f'Трек {current_track_title} поставлен на паузу')

    @bot.tree.command(name='resume', description='Снять паузу с трека')
    async def resume_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_paused():
            current_track_title = queue[0][1]
            voice_client.resume()
            await interaction.response.send_message(f'Трек {current_track_title} снят с паузы')

    @bot.tree.command(name='queue', description='Показать очередь')
    async def show_queue(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client:
            queue_content = str()

            for number, track in enumerate(queue, 1):
                queue_content += f'{number}. **{track[1]}**\n'

            await interaction.response.send_message(queue_content)

    bot.run(TOKEN)


if __name__ == '__main__':
    main()
