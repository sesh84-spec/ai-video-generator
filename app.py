import os
import threading
import uuid

from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv

from request import generate_video, VideoGenerationError

load_dotenv()

app = Flask(__name__)

tasks = {}
tasks_lock = threading.Lock()


def set_task(task_id: str, data: dict) -> None:
    with tasks_lock:
        tasks[task_id] = data


def get_task(task_id: str):
    with tasks_lock:
        return tasks.get(task_id)


def build_message_text(status: str) -> str:
    mapping = {
        "queued": "Задача поставлена в очередь",
        "started": "Генерация видео началась",
        "in_progress": "Видео генерируется",
        "downloading": "Скачивание видео",
        "completed": "Генерация завершена",
        "failed": "Генерация не удалась",
        "error": "Произошла ошибка",
    }
    return mapping.get(status, "Обработка")


def generate_video_with_progress(prompt: str, task_id: str) -> None:
    os.makedirs("generated", exist_ok=True)
    video_path = os.path.join("generated", f"video_{task_id}.mp4")

    def progress_callback(status: str, progress: float, data: dict) -> None:
        video_id = data.get("id") or data.get("video_id")

        set_task(
            task_id,
            {
                "status": status,
                "progress": progress,
                "message": build_message_text(status),
                "video_id": video_id,
                "video_path": video_path if status == "completed" else None,
            },
        )

    try:
        result = generate_video(
            prompt=prompt,
            output_path=video_path,
            progress_callback=progress_callback,
            poll_interval=10,
        )

        set_task(
            task_id,
            {
                "status": "completed",
                "progress": 100,
                "message": "Генерация завершена",
                "video_id": result["video_id"],
                "video_path": result["video_path"],
            },
        )

    except VideoGenerationError as error:
        set_task(
            task_id,
            {
                "status": "failed",
                "progress": 100,
                "message": str(error),
                "video_id": None,
                "video_path": None,
            },
        )

    except Exception as error:
        set_task(
            task_id,
            {
                "status": "error",
                "progress": 0,
                "message": str(error),
                "video_id": None,
                "video_path": None,
            },
        )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "Промпт не может быть пустым"}), 400

    task_id = str(uuid.uuid4())

    set_task(
        task_id,
        {
            "status": "queued",
            "progress": 0,
            "message": "Задача поставлена в очередь",
            "video_id": None,
            "video_path": None,
        },
    )

    thread = threading.Thread(
        target=generate_video_with_progress,
        args=(prompt, task_id),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/status/<task_id>")
def status(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "Задача не найдена"}), 404
    return jsonify(task)


@app.route("/download/<task_id>")
def download(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "Задача не найдена"}), 404

    video_path = task.get("video_path")
    if not video_path:
        return jsonify(
            {
                "error": "Видео ещё не готово",
                "status": task.get("status"),
                "message": task.get("message"),
            }
        ), 400

    if not os.path.exists(video_path):
        return jsonify(
            {
                "error": "Файл не найден на диске",
                "video_path": video_path,
                "status": task.get("status"),
            }
        ), 404

    return send_file(
        video_path,
        as_attachment=True,
        download_name="video.mp4",
        mimetype="video/mp4",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)