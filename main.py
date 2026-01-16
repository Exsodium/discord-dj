from dotenv import load_dotenv
from os import getenv
from discord import Intents, Interaction, app_commands, FFmpegOpusAudio, Embed
from discord.ext import commands
import logging
from yt_dlp import YoutubeDL
from asyncio import get_event_loop, run_coroutine_threadsafe, create_task
from collections import deque
from random import choice
from pathlib import Path

load_dotenv()
TOKEN = getenv('TOKEN')
YDL_OPTIONS = {
    'format': 'bestaudio[abr<=96]/bestaudio',
    'youtube_include_dash_manifest': False,
    'youtube_include_hls_manifest': False,
    'skip_download': True,
    'geo_bypass': True,
}
FFMPEG_OPTIONS = ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -c:a libopus -b:a 96k',
    'executable': 'ffmpeg/ffmpeg.exe'
}
logger = logging.getLogger(__name__)


async def search_ytdlp_async(query, ydl_opts):
    loop = get_event_loop()
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

        if not interaction.user.voice:
            await interaction.followup.send('**Вы должны быть в голосовом канале!**', ephemeral=True)
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
            await interaction.followup.send('Трек не найден!', ephemeral=True)
            return

        track: dict = entries[0]
        track_data = {
            'url': track['url'],
            'title': track['title'],
            'duration': track['duration']
        }

        queue.append(track_data)

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f'Добавлено в очередь: **{track_data['title']}**')
        else:
            await play_next_track(voice_client, interaction.channel)

    async def play_next_track(voice_client, channel) -> None:
        if queue:
            current_track_data = queue[0]
            source = FFmpegOpusAudio(
                current_track_data['url'],
                **FFMPEG_OPTIONS,
            )

            def after_play(error):
                if error:
                    logger.error(f"Ошибка воспроизведения: {error}")

                queue.popleft()

                run_coroutine_threadsafe(
                    play_next_track(voice_client, channel),
                    bot.loop
                )

            voice_client.play(source, after=after_play)
            create_task(
                channel.send(
                    f'Сейчас играет: **{current_track_data['title']}**')
            )
        else:
            await voice_client.disconnect()

    @bot.tree.command(name='skip', description='Пропустить трек')
    async def skip_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            current_track_title = queue[0]['title']
            voice_client.stop()
            await interaction.response.send_message(f'Пропущен: **{current_track_title}**')
        else:
            await interaction.response.send_message('Ничего не играет!', ephemeral=True)

    @bot.tree.command(name='pause', description='Поставить трек на паузу')
    async def pause_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_playing():
            current_track_title = queue[0]['title']
            voice_client.pause()
            await interaction.response.send_message(f'Поставлен на паузу: **{current_track_title}**')

    @bot.tree.command(name='resume', description='Снять паузу с трека')
    async def resume_track(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_paused():
            current_track_title = queue[0]['title']
            voice_client.resume()
            await interaction.response.send_message(f'Снят с паузы: **{current_track_title}**')

    @bot.tree.command(name='queue', description='Показать очередь')
    async def show_queue(interaction: Interaction) -> None:
        voice_client = interaction.guild.voice_client

        if voice_client:
            queue_content = str()

            for number, track in enumerate(queue, 1):
                duration = track['duration']
                minutes = duration // 60
                seconds = duration % 60

                queue_content += f'{number}. **{track['title']}** {minutes}:{seconds:02d}\n'

            embed = Embed(
                title='Очередь',
                description=queue_content
            )

            await interaction.response.send_message(embed=embed)

    @bot.tree.command(name='perd', description='Проиграть запись гения, опердившего своё время')
    async def play_voice(interaction: Interaction) -> None:
        if not interaction.user.voice:
            await interaction.followup.send('**Вы должны быть в голосовом канале!**', ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        else:
            await voice_client.move_to(voice_channel)

        voices = Path('voices')
        track = choice(list(voices.iterdir()))
        source = FFmpegOpusAudio(
            track,
            executable='ffmpeg/ffmpeg.exe'
        )

        if voice_client.is_playing():
            voice_client.pause()
            current_source = voice_client.source

            def after_voice(error):
                if error:
                    logger.error(f"Ошибка воспроизведения: {error}")

                channel = interaction.channel

                def after_play(error):
                    if error:
                        logger.error(f"Ошибка воспроизведения: {error}")

                    queue.popleft()

                    run_coroutine_threadsafe(
                        play_next_track(voice_client, channel),
                        bot.loop
                    )

                voice_client.play(current_source, after=after_play)

            voice_client.play(source, after=after_voice)
        else:
            voice_client.play(source)

        await interaction.response.send_message('Чё мгс петувшки, больше слушать неченго?')

    bot.run(TOKEN)


if __name__ == '__main__':
    main()
