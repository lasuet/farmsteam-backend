from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import json

DB_PATH = "farmsteam.db"

app = FastAPI(title="FarmSteam backend")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

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


class StateIn(BaseModel):
    user_id: str
    state: dict


class ReferralIn(BaseModel):
    referrer_id: str
    friend_id: str


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


@app.get("/state/{user_id}")
def get_state(user_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT state_json FROM user_state WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    conn.close()

    if not row:
        return DEFAULT_STATE

    try:
        saved = json.loads(row["state_json"])
        merged = DEFAULT_STATE.copy()
        merged.update(saved)
        return merged
    except Exception:
        return DEFAULT_STATE


@app.post("/state")
def save_state(payload: StateIn):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO user_state (user_id, state_json) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET state_json = excluded.state_json",
        (payload.user_id, json.dumps(payload.state)),
    )

    conn.commit()
    conn.close()

    return {"ok": True}


@app.post("/referral/register")
def register_referral(data: ReferralIn):
    if data.referrer_id == data.friend_id:
        raise HTTPException(status_code=400, detail="self-ref")

    conn = get_conn()
    cur = conn.cursor()

    # уже был учтён такой друг
    cur.execute("SELECT 1 FROM referrals WHERE friend_id = ?", (data.friend_id,))
    if cur.fetchone():
        conn.close()
        return {"ok": True, "already": True}

    # записываем пару
    cur.execute(
        "INSERT INTO referrals (friend_id, referrer_id) VALUES (?, ?)",
        (data.friend_id, data.referrer_id),
    )

    bonus = 10_000

    # начисляем бонус рефереру и другу
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
