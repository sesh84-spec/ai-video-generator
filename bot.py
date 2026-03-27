import os
import threading

import telebot
from dotenv import load_dotenv

from request import generate_video, VideoGenerationError

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = telebot.TeleBot(BOT_TOKEN)

# Хранилище задач пользователей в памяти процесса
user_tasks = {}
tasks_lock = threading.Lock()


def set_user_task(user_id: int, data: dict) -> None:
    with tasks_lock:
        user_tasks[user_id] = data


def get_user_task(user_id: int):
    with tasks_lock:
        return user_tasks.get(user_id)


def build_message_text(status: str, fallback: str = "") -> str:
    mapping = {
        "started": "Генерация видео началась",
        "queued": "Видео в очереди",
        "in_progress": "Видео генерируется",
        "downloading": "Скачивание видео",
        "completed": "Генерация завершена",
        "failed": "Генерация не удалась",
        "error": "Произошла ошибка",
    }
    return fallback or mapping.get(status, "Обработка")


def update_progress_message(user_id: int, message_id: int, status: str, progress: float, message_text: str) -> None:
    try:
        bar_length = 20
        filled_length = int((progress / 100) * bar_length)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)

        status_emoji = {
            "started": "🚀",
            "queued": "⏳",
            "in_progress": "⚙️",
            "downloading": "⬇️",
            "completed": "✅",
            "failed": "❌",
            "error": "❌",
        }

        emoji = status_emoji.get(status, "⏳")
        text = f"{emoji} {message_text}\n\n[{bar}] {progress:.1f}%"

        bot.edit_message_text(
            text,
            chat_id=user_id,
            message_id=message_id,
        )
    except Exception:
        # Игнорируем ошибки редактирования сообщения
        pass


def generate_video_with_progress(prompt: str, user_id: int, message_id: int) -> None:
    video_path = f"video_{user_id}_{message_id}.mp4"
    sent_successfully = False

    def progress_callback(status: str, progress: float, data: dict) -> None:
        video_id = data.get("id") or data.get("video_id")
        message = build_message_text(status)

        if status == "failed":
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message") or message

        if status == "completed":
            message = "Генерация завершена"

        set_user_task(
            user_id,
            {
                "status": status,
                "progress": progress,
                "message": message,
                "video_id": video_id,
                "video_path": video_path if status == "completed" else None,
            },
        )
        update_progress_message(user_id, message_id, status, progress, message)

    try:
        result = generate_video(
            prompt=prompt,
            output_path=video_path,
            progress_callback=progress_callback,
            poll_interval=10,
        )

        with open(result["video_path"], "rb") as video_file:
            bot.send_video(user_id, video_file, caption="✅ Видео готово!")
        sent_successfully = True

        update_progress_message(
            user_id,
            message_id,
            "completed",
            100,
            "Видео готово и отправлено выше",
        )

        set_user_task(
            user_id,
            {
                "status": "completed",
                "progress": 100,
                "message": "Видео готово и отправлено",
                "video_id": result["video_id"],
                "video_path": result["video_path"],
            },
        )

    except VideoGenerationError as error:
        set_user_task(
            user_id,
            {
                "status": "failed",
                "progress": 100,
                "message": str(error),
                "video_id": None,
                "video_path": None,
            },
        )
        update_progress_message(user_id, message_id, "failed", 100, str(error))

    except Exception as error:
        set_user_task(
            user_id,
            {
                "status": "error",
                "progress": 0,
                "message": str(error),
                "video_id": None,
                "video_path": None,
            },
        )
        update_progress_message(user_id, message_id, "error", 0, f"Ошибка: {error}")

    finally:
        if sent_successfully and os.path.exists(video_path):
            os.remove(video_path)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    text = (
        "🎬 Добро пожаловать в бота для генерации видео.\n\n"
        "Отправьте текстовое описание сцены, и бот запустит генерацию.\n\n"
        "Пример:\n"
        "Современный загородный дом среди сосновых деревьев на закате, "
        "тёплый свет в окнах, спокойное движение камеры вперёд."
    )
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    prompt = message.text.strip()

    if not prompt:
        bot.reply_to(message, "❌ Пожалуйста, отправьте описание видео.")
        return

    current_task = get_user_task(message.from_user.id)
    if current_task and current_task["status"] in ("started", "queued", "in_progress", "downloading"):
        bot.reply_to(
            message,
            "⏳ У вас уже есть активная задача. Дождитесь её завершения.",
        )
        return

    progress_msg = bot.reply_to(
        message,
        "🚀 Генерация видео началась...\n\n[░░░░░░░░░░░░░░░░░░░░] 0.0%",
    )

    thread = threading.Thread(
        target=generate_video_with_progress,
        args=(prompt, message.from_user.id, progress_msg.message_id),
        daemon=True,
    )
    thread.start()


if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(skip_pending=True)