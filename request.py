import os
import time
from typing import Callable, Optional, Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.proxyapi.ru/openai/v1"
DEFAULT_MODEL = "sora-2"
DEFAULT_SECONDS = "4"


class VideoGenerationError(Exception):
    """Ошибка генерации или скачивания видео через Proxy API."""


def _get_api_key() -> str:
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise VideoGenerationError("API_KEY не найден в .env")
    return api_key


def _json_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
    }


def _safe_json(response: requests.Response, context: str) -> Dict[str, Any]:
    try:
        return response.json()
    except Exception as exc:
        raise VideoGenerationError(
            f"{context}: сервер вернул не JSON. Ответ: {response.text}"
        ) from exc


def create_video_job(
    prompt: str,
    model: str = DEFAULT_MODEL,
    seconds: str = DEFAULT_SECONDS,
    size: Optional[str] = None,
) -> Dict[str, Any]:
    """Создать задачу генерации видео и вернуть ответ API."""
    if not prompt or not prompt.strip():
        raise VideoGenerationError("Промпт не может быть пустым")

    payload = {
        "model": model,
        "prompt": prompt.strip(),
        "seconds": str(seconds),
    }

    if size:
        payload["size"] = size

    response = requests.post(
        f"{BASE_URL}/videos",
        headers=_json_headers(),
        json=payload,
        timeout=60,
    )

    if response.status_code not in (200, 201):
        raise VideoGenerationError(
            f"Ошибка при создании видео: {response.text}"
        )

    data = _safe_json(response, "Создание видео")

    if not data.get("id"):
        raise VideoGenerationError(f"API не вернул ID видео: {data}")

    return data


def get_video_status(video_id: str) -> Dict[str, Any]:
    """Получить текущий статус генерации по video_id."""
    response = requests.get(
        f"{BASE_URL}/videos/{video_id}",
        headers=_auth_headers(),
        timeout=60,
    )

    if response.status_code != 200:
        raise VideoGenerationError(
            f"Ошибка при получении статуса: {response.text}"
        )

    return _safe_json(response, "Получение статуса")


def wait_for_video(
    video_id: str,
    poll_interval: int = 10,
    progress_callback: Optional[
        Callable[[str, float, Dict[str, Any]], None]
    ] = None,
) -> Dict[str, Any]:
    """
    Ждать завершения генерации.
    progress_callback(status, progress, raw_status_data)
    """
    while True:
        status_data = get_video_status(video_id)
        status = status_data.get("status", "unknown")
        progress = float(status_data.get("progress", 0) or 0)

        if progress_callback:
            progress_callback(status, progress, status_data)

        if status == "completed":
            return status_data

        if status == "failed":
            error = status_data.get("error")
            if isinstance(error, dict):
                message = error.get("message") or str(error)
            else:
                message = str(error) if error else "Генерация видео не удалась"
            raise VideoGenerationError(message)

        time.sleep(max(2, poll_interval))


def download_video(
    video_id: str,
    output_path: str = "video.mp4",
    variant: str = "video",
) -> str:
    """Скачать готовое видео."""
    params = {}
    if variant and variant != "video":
        params["variant"] = variant

    response = requests.get(
        f"{BASE_URL}/videos/{video_id}/content",
        headers=_auth_headers(),
        params=params,
        stream=True,
        timeout=300,
    )

    if response.status_code != 200:
        raise VideoGenerationError(
            f"Ошибка при скачивании файла: {response.text}"
        )

    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(output_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)

    if not os.path.exists(output_path):
        raise VideoGenerationError("Файл не был создан после скачивания")

    return output_path


def generate_video(
    prompt: str,
    output_path: str = "video.mp4",
    model: str = DEFAULT_MODEL,
    seconds: str = DEFAULT_SECONDS,
    size: Optional[str] = None,
    poll_interval: int = 10,
    progress_callback: Optional[
        Callable[[str, float, Dict[str, Any]], None]
    ] = None,
) -> Dict[str, Any]:
    """
    Полный цикл:
    create -> wait -> download
    Возвращает:
    {
        "video_id": ...,
        "video_path": ...,
        "status": "completed",
        "raw": ...
    }
    """
    created = create_video_job(
        prompt=prompt,
        model=model,
        seconds=seconds,
        size=size,
    )
    video_id = created["id"]

    if progress_callback:
        progress_callback("started", 0.0, created)

    completed = wait_for_video(
        video_id=video_id,
        poll_interval=poll_interval,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback("downloading", 95.0, completed)

    video_path = download_video(video_id=video_id, output_path=output_path)

    final_data = dict(completed)
    final_data["video_path"] = video_path

    if progress_callback:
        progress_callback("completed", 100.0, final_data)

    return {
        "video_id": video_id,
        "video_path": video_path,
        "status": "completed",
        "raw": final_data,
    }


if __name__ == "__main__":
    print("Модуль request.py готов. Используйте bot.py или app.py.")