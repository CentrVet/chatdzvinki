import os
import time
import requests
from typing import Optional

import config


class PhonetClient:
    """Клиент для API АТС Phonet.

    Авторизация один раз, cookie JSESSIONID сохраняется в сессии.
    При 403 повторяет авторизацию автоматически.
    """

    def __init__(self):
        self.domain = config.PHONET_DOMAIN
        self.api_key = config.PHONET_API_KEY
        self.base = f"https://{self.domain}"
        self.session = requests.Session()
        self._authorized = False

    def _authorize(self):
        r = self.session.post(
            f"{self.base}/rest/security/authorize",
            json={"domain": self.domain, "apiKey": self.api_key},
            timeout=20,
        )
        r.raise_for_status()
        self._authorized = True

    def _request(self, method: str, path: str, **kwargs):
        if not self._authorized:
            self._authorize()
        r = self.session.request(method, f"{self.base}{path}", timeout=30, **kwargs)
        if r.status_code == 403:
            self._authorize()
            r = self.session.request(method, f"{self.base}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r

    def list_company_calls(
        self,
        time_from_ms: int,
        time_to_ms: int,
        directions: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict]:
        """GET /rest/calls/company.api — список совершённых звонков за период.

        Пагинирует сам, пока не выгребет всё.
        """
        all_calls = []
        offset = 0
        while True:
            params = {
                "timeFrom": time_from_ms,
                "timeTo": time_to_ms,
                "limit": limit,
                "offset": offset,
            }
            if directions is not None:
                params["directions"] = directions
            r = self._request("GET", "/rest/calls/company.api", params=params)
            batch = r.json()
            if not batch:
                break
            all_calls.extend(batch)
            if len(batch) < limit:
                break
            offset += len(batch)
            time.sleep(1)  # Phonet rate limit
        return all_calls

    def download_audio(self, uuid: str, save_path: str) -> str | None:
        """Качает запись звонка. Возвращает путь к файлу или None если записи нет (400)."""
        if not self._authorized:
            self._authorize()
        url = f"{self.base}/rest/public/calls/{uuid}/audio"
        with self.session.get(url, stream=True, timeout=60) as r:
            if r.status_code == 403:
                self._authorize()
                r = self.session.get(url, stream=True, timeout=60)
            if r.status_code in (400, 404):
                return None
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return save_path


def ms_now() -> int:
    return int(time.time() * 1000)
