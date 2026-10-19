# Бот контроля качества кол-центра ветклиники

Опрашивает Phonet API, скачивает записи входящих звонков, расшифровывает локальным Whisper, оценивает через Claude и шлёт отчёт в Telegram.

## Что нужно установить

### 1. Python 3.10+
Скачать с https://python.org — при установке галочка **"Add Python to PATH"**.

### 2. FFmpeg (нужен для Whisper)
Самый простой способ через winget (встроенный в Windows 10/11):
```powershell
winget install Gyan.FFmpeg
```
После установки — **перезапустить PowerShell**, проверить:
```powershell
ffmpeg -version
```

### 3. Зависимости Python
В папке `D:\bot`:
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

1. Скопировать `.env.example` в `.env`:
   ```powershell
   copy .env.example .env
   ```
2. Открыть `.env` и заполнить:
   - `ANTHROPIC_API_KEY` — ключ с https://console.anthropic.com
   - `TELEGRAM_BOT_TOKEN` — от @BotFather
   - `TELEGRAM_CHAT_ID` — от @userinfobot (ваш личный id или id группы)

Phonet-данные уже вписаны.

## Проверка

```powershell
venv\Scripts\activate
python test_connection.py
```
Должны пройти все 3 проверки, в Telegram придёт тестовое сообщение.

## Запуск

**Разовый прогон** (обработает звонки за последние 15 минут):
```powershell
python main.py
```

**Постоянный режим** (опрашивает каждые 10 минут):
```powershell
python main.py --loop
```

**Через Windows Task Scheduler** (рекомендую для продакшена):
1. Открыть "Планировщик заданий"
2. Создать задачу: Триггер — каждые 10 минут
3. Действие — Запуск программы:
   - Программа: `D:\bot\venv\Scripts\python.exe`
   - Аргументы: `main.py`
   - Рабочая папка: `D:\bot`

При первом запуске Whisper скачает модель (~500 МБ) в `~/.cache/huggingface`. Дальше — уже из кэша.

## Производительность

Для `WHISPER_MODEL=small` на обычном Windows-компьютере без видеокарты:
- Звонок 3 минуты расшифровывается ~30-60 сек
- Оценка Claude Haiku ~2-3 сек
- Один цикл на 10 новых звонков ≈ 10 минут

Если не успевает — поставьте `WHISPER_MODEL=base` (быстрее, но менее точно).

## Фильтры

В `.env`:
- `MIN_DURATION_SECONDS=20` — не анализируем звонки короче 20 сек (гудки, недозвоны)
- `DIRECTIONS=4` — только входящие (клиенты в клинику). `2` — только исходящие, не указывать — все.

## Логика

- При старте — авторизация в Phonet (сохраняется cookie)
- Запрос звонков за `POLL_WINDOW_MINUTES` (по умолчанию 15 мин) назад
- Для каждого нового (не из `processed.db`) звонка:
  1. Скачать mp3
  2. Прогнать через Whisper → текст
  3. Отправить текст в Claude Haiku с промптом из `analyze.py`
  4. Получить JSON `{summary, score, risk, reason, fix}`
  5. Отформатировать и отправить в Telegram
  6. Записать uuid в SQLite (`processed.db`)
  7. Удалить mp3 из кэша
- Короткие звонки и звонки без записи помечаются как обработанные с `risk=-1`, но не анализируются

## Структура файлов

- `config.py` — загрузка `.env`
- `phonet.py` — клиент Phonet API (авторизация, список звонков, скачивание аудио)
- `transcribe.py` — faster-whisper, локальная расшифровка
- `analyze.py` — Claude API, оценка по вашему промпту
- `notify.py` — отправка в Telegram
- `db.py` — SQLite для дедупликации
- `main.py` — основной цикл
- `test_connection.py` — проверка всех трёх подключений
