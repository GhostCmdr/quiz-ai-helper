import json
import os
from datetime import datetime

MAX_RECORDS = 500


def load_history(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict) and r.get("q")]
    except (OSError, json.JSONDecodeError):
        return []


def save_history(path, records):
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            return
        with open(path, "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=1)
    except OSError:
        pass


def add_record(path, records, question, answer):
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        return
    updated = [r for r in records if r.get("q") != question]
    updated.insert(0, {"q": question, "a": answer,
                       "t": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    if len(updated) > MAX_RECORDS:
        updated = updated[:MAX_RECORDS]
    save_history(path, updated)
    return updated