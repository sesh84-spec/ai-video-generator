import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")
video_id = "video_69c38d340908819097901d8c6e25194206d5254bcdcaa90b"

url = f"https://api.proxyapi.ru/openai/v1/videos/{video_id}"

headers = {
    "Authorization": f"Bearer {api_key}"
}

response = requests.get(url, headers=headers)

if response.status_code != 200:
    print("Ошибка при получении статуса:")
    print(response.text)
else:
    data = response.json()
    print("ID:", data.get("id"))
    print("Статус:", data.get("status"))
    print("Прогресс:", data.get("progress"))
    print("Модель:", data.get("model"))