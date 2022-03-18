from config import IMGUR_CLIENT_ID
import requests
from retry import retry
import json
import time


# You can change this function to any other service you'd like.
@retry(requests.exceptions.HTTPError, tries=5, delay=1, backoff=2, jitter=(0, 2))
def upload_image(path: str, logger) -> str:
    """
    Uploads an image to an image hosting website (Imgur).
    :param path: The path of the image to upload
    :return: The URL of the newly uploaded image.
    """
    try:
        response = requests.post(
            "https://api.imgur.com/3/upload",
            headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"},
            files={"image": open(path, "rb")},
        )
        response.raise_for_status()
        resp_json = json.loads(response.text)
        return resp_json["data"]["link"]
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            retry_after = int(e.response.headers['X-Post-Rate-Limit-Reset'])
            logger.warning(f'Imgur rate limit reached, waiting {retry_after} seconds to upload image...')
            time.sleep(retry_after)
        raise
