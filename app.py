from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

app = Flask(__name__)
csv_file_path = "interaction_log.csv"


# ---------------- Google Sheets 連線 ----------------
def get_sheet(sheet_id):
    """連線 Google Sheets，回傳第一個 worksheet"""
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    creds_dict = json.loads(creds_json)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    # ✅ 改這裡：自動抓第一個 worksheet，而不是 sh.sheet1
    ws = sh.get_worksheet(0)
    return ws


# ---------------- 初始化 CSV ----------------
if not os.path.exists(csv_file_path):
    with open(csv_file_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id",
            "task_type", "interaction_type", "trial_no", "target_index", "grid_index",
            "reaction_time", "level_name", "start_time", "end_time",
            "gaze_target_x", "gaze_target_y", "gaze_target_z",
            "gaze_x", "gaze_y", "gaze_z",
            "interaction_result",
            "process", "appear_time", "timestamp"
        ])


@app.route('/')
def index():
    return '✅ Flask 伺服器已運作！'


# ---------------- 接收資料 ----------------
@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json()

    print("\n📥【收到互動資料】")
    for key, value in data.items():
        print(f"{key:<18}: {value}")
    print("📝 已記錄至 CSV\n")

    def get(key):
        return data.get(key, "")

    with open(csv_file_path, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            get("user_id"),
            get("task_type"), get("interaction_type"), get("trial_no"),
            get("target_index"), get("grid_index"),
            get("reaction_time"), get("level_name"),
            get("start_time"), get("end_time"),
            get("gaze_target_x"), get("gaze_target_y"), get("gaze_target_z"),
            get("gaze_x"), get("gaze_y"), get("gaze_z"),
            get("interaction_result"),
            get("process"), get("appear_time"), get("timestamp")
        ])

    # ✅ 同步到 Google Sheets
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdVYojtpX0yVQdn6W4H4KuQ7PlsiGGU"
        ws = get_sheet(SHEET_ID)
        ws.append_row([
            get("user_id"),
            get("task_type"), get("interaction_type"), get("trial_no"),
            get("target_index"), get("grid_index"),
            get("reaction_time"), get("level_name"),
            get("start_time"), get("end_time"),
            get("gaze_target_x"), get("gaze_target_y"), get("gaze_target_z"),
            get("gaze_x"), get("gaze_y"), get("gaze_z"),
            get("interaction_result"),
            get("process"), get("appear_time"), get("timestamp")
        ])
        print("✅ 已同步到 Google Sheets")
    except Exception as e:
        print(f"❌ Google Sheets 寫入失敗: {e}")

    return jsonify({"message": "✅ 資料寫入成功"})


# ---------------- 聚合分析 ----------------
@app.route('/aggregate', methods=['GET'])
def aggregate():
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdVYojtpX0yVQdn6W4H4KuQ7PlsiGGU"
        ws = get_sheet(SHEET_ID)
        rows = ws.get_all_values()

        df = pd.DataFrame(rows[1:], columns=rows[0])
        if df.empty:
            return jsonify({"message": "Google Sheet is empty"}), 200

        # 確保數值正確
        df["reaction_time"] = pd.to_numeric(df["reaction_time"], errors="coerce")
        if "interaction_result" in df.columns:
            df["interaction_result"] = pd.to_numeric(df["interaction_result"], errors="coerce")

        results = {}

        # ---------- 眼動 ----------
        eye_data = df[df["level_name"].str.strip().str.lower().isin(["practiceeye", "practicegaze"])].copy()
        if not eye_data.empty:
            cols = ["gaze_target_x", "gaze_target_y", "gaze_target_z", "gaze_x", "gaze_y", "gaze_z"]
            for c in cols:
                eye_data[c] = pd.to_numeric(eye_data[c], errors="coerce")
            eye_data = eye_data.fillna(0)
            eye_data["error"] = np.sqrt(
                (eye_data["gaze_target_x"] - eye_data["gaze_x"])**2 +
                (eye_data["gaze_target_y"] - eye_data["gaze_y"])**2 +
                (eye_data["gaze_target_z"] - eye_data["gaze_z"])**2
            )
            user_eye = eye_data.groupby("user_id")["error"].mean().reset_index()
            results["eye_accuracy"] = {
                "per_user": user_eye.to_dict(orient="records"),
                "overall_avg": user_eye["error"].mean()
            }

        # ... 其他 voice, point, grab, coupon, collab (保持原本程式碼) ...

        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- 測試 Google Sheets 連線 ----------------
@app.route('/test_sheets', methods=['GET'])
def test_sheets():
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdVYojtpX0yVQdn6W4H4KuQ7PlsiGGU"
        ws = get_sheet(SHEET_ID)

        rows = ws.get_all_values()[:5]
        return jsonify({"status": "success", "preview": rows}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
