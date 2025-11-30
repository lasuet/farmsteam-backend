from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import json
import logging

# Путь к базе данных SQLite
DB_PATH = "farmsteam.db"

# Инициализация FastAPI
app = FastAPI(title="FarmSteam backend")

# Логирование
logging.basicConfig(level=logging.INFO)

# Функция подключения к базе данных
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация базы данных
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Создание таблиц, если они не существуют
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_state (
        user_id TEXT PRIMARY KEY,
        state_json TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        friend_id TEXT PRIMARY KEY,
        referrer_id TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()

# Pydantic модели для валидации данных
class StateIn(BaseModel):
    user_id: str
    state: dict

class ReferralIn(BaseModel):
    referrer_id: str
    friend_id: str

# Значения по умолчанию для состояния пользователя
DEFAULT_STATE = {
    "coins": 0,
    "clickLevel": 1,
    "clickValue": 1,
    "energyLevel": 1,
    "maxEnergy": 10,
    "energy": 10,
    "autoLevel": 1,
    "regenLevel": 1,
    "energyRegenRate": 1.0,
    "lastEnergyAt": 0,
    "lastIncomeAt": 0,
    "farms": [],
    "clickCount": 0,
    "totalEarned": 0,
    "quests": {},
    "achievements": {},
    "level": 1,
    "steam_rub": 0,
}

@app.on_event("startup")
def on_startup():
    init_db()

# Обработка GET-запроса для получения состояния пользователя
@app.get("/state/{user_id}")
def get_state(user_id: str):
    conn = get_conn()
    cur = conn.cursor()

    # Запрос на получение состояния пользователя из базы данных
    cur.execute("SELECT state_json FROM user_state WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    # Если пользователь не найден, возвращаем значения по умолчанию
    if not row:
        logging.info(f"Данных для пользователя {user_id} нет, возвращаем значения по умолчанию.")
        return DEFAULT_STATE

    try:
        # Загружаем сохраненные данные и объединяем с данными по умолчанию
        saved = json.loads(row["state_json"])
        merged = DEFAULT_STATE.copy()
        merged.update(saved)
        logging.info(f"Данные для пользователя {user_id} успешно загружены.")
        return merged
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных для пользователя {user_id}: {e}")
        return DEFAULT_STATE

# Обработка POST-запроса для сохранения состояния пользователя
@app.post("/state")
def save_state(payload: StateIn):
    conn = get_conn()
    cur = conn.cursor()

    # Логируем входящие данные
    logging.info(f"Получены данные для сохранения пользователя {payload.user_id}: {payload.state}")

    try:
        # Пытаемся сохранить или обновить данные в базе
        cur.execute(
            "INSERT INTO user_state (user_id, state_json) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET state_json = excluded.state_json",
            (payload.user_id, json.dumps(payload.state)),
        )
        conn.commit()
        logging.info(f"Данные для пользователя {payload.user_id} успешно сохранены.")
    except sqlite3.Error as e:
        # Логируем ошибку с деталями
        logging.error(f"SQLite ошибка при сохранении данных для пользователя {payload.user_id}: {e}")
        conn.close()
        raise HTTPException(status_code=500, detail="Ошибка при сохранении данных")
    except Exception as e:
        # Логируем все другие ошибки
        logging.error(f"Ошибка при сохранении данных для пользователя {payload.user_id}: {e}")
        conn.close()
        raise HTTPException(status_code=500, detail="Ошибка при сохранении данных")

    conn.close()
    return {"ok": True}

# Обработка POST-запроса для регистрации реферальной ссылки
@app.post("/referral/register")
def register_referral(data: ReferralIn):
    if data.referrer_id == data.friend_id:
        raise HTTPException(status_code=400, detail="self-ref")

    conn = get_conn()
    cur = conn.cursor()

    # Проверяем, был ли уже учтен такой друг
    cur.execute("SELECT 1 FROM referrals WHERE friend_id = ?", (data.friend_id,))
    if cur.fetchone():
        conn.close()
        return {"ok": True, "already": True}

    # Записываем пару
    cur.execute(
        "INSERT INTO referrals (friend_id, referrer_id) VALUES (?, ?)",
        (data.friend_id, data.referrer_id),
    )

    bonus = 10_000  # Бонус за реферала

    # Начисляем бонус как рефереру, так и другу
    for uid in (data.referrer_id, data.friend_id):
        cur.execute("SELECT state_json FROM user_state WHERE user_id = ?", (uid,))
        row = cur.fetchone()

        if row:
            st = json.loads(row["state_json"])
        else:
            st = DEFAULT_STATE.copy()

        st["coins"] = st.get("coins", 0) + bonus

        cur.execute(
            "INSERT INTO user_state (user_id, state_json) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET state_json = excluded.state_json",
            (uid, json.dumps(st)),
        )

    conn.commit()
    conn.close()

    return {"ok": True, "bonus": bonus}
