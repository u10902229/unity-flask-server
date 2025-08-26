from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime
import pandas as pd
import numpy as np
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
csv_file_path = "interaction_log.csv"

# ---------------- Google Sheets 初始化 ----------------
def get_sheet(spreadsheet_id: str, worksheet_title: str = None):
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        raise RuntimeError("❌ GOOGLE_SERVICE_ACCOUNT_JSON not set in environment variables")

    creds_dict = json.loads(sa_json)
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(spreadsheet_id)
    if worksheet_title:
        ws = sh.worksheet(worksheet_title)   # 指定分頁
    else:
        ws = sh.sheet1                       # 預設第一個分頁（目前是「工作表1」）
    return ws


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
    print("📝 已記錄\n")

    def get(key):
        return data.get(key, "")

    row = [
        get("user_id"),
        get("task_type"), get("interaction_type"), get("trial_no"),
        get("target_index"), get("grid_index"),
        get("reaction_time"), get("level_name"),
        get("start_time"), get("end_time"),
        get("gaze_target_x"), get("gaze_target_y"), get("gaze_target_z"),
        get("gaze_x"), get("gaze_y"), get("gaze_z"),
        get("interaction_result"),
        get("process"), get("appear_time"), get("timestamp")
    ]

    # 1️⃣ 照舊寫入 CSV（方便本地 debug）
    with open(csv_file_path, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)

    # 2️⃣ 同步到 Google Sheets
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdYVojtpX0yVQdn6W4H4KuQ7PlsiGGU"  # ✅ 你的試算表 ID
        ws = get_sheet(SHEET_ID, "工作表1")                       # ✅ 指定「工作表1」
        ws.append_row(row)
        print("✅ 已同步到 Google Sheets")
    except Exception as e:
        print("⚠️ Google Sheets 同步失敗:", e)

    return jsonify({"message": "✅ 資料寫入成功"})


# ---------------- 聚合分析 ----------------
@app.route('/aggregate', methods=['GET'])
def aggregate():
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdYVojtpX0yVQdn6W4H4KuQ7PlsiGGU"
        ws = get_sheet(SHEET_ID, "工作表1")

        # 讀取 Google Sheets 全部資料（包含表頭）
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return jsonify({"message": "Google Sheet is empty"}), 200

        # 轉成 DataFrame
        df = pd.DataFrame(rows[1:], columns=rows[0])  # 第一列當表頭
        if df.empty:
            return jsonify({"message": "Google Sheet empty"}), 200

        # 確保數值型欄位正確
        df["reaction_time"] = pd.to_numeric(df["reaction_time"], errors="coerce")
        if "interaction_result" in df.columns:
            df["interaction_result"] = pd.to_numeric(df["interaction_result"], errors="coerce")

        results = {}

        # ---------- 1. 眼動 ----------
        eye_data = df[df["level_name"].str.strip().str.lower() == "practiceeye"].copy()
        if not eye_data.empty:
            cols = ["gaze_target_x", "gaze_target_y", "gaze_target_z",
                    "gaze_x", "gaze_y", "gaze_z"]
            for c in cols:
                eye_data[c] = pd.to_numeric(eye_data[c], errors="coerce")
            eye_data = eye_data.dropna(subset=cols)

            if not eye_data.empty:
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

        # ---------- 2. 語音 ----------
        voice_data = df[df["level_name"] == "practicevoice"].copy()
        if not voice_data.empty:
            user_voice = voice_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_voice.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["voice_accuracy"] = {
                "per_user": user_voice.to_dict(orient="records"),
                "overall_avg": user_voice["accuracy"].mean()
            }

        # ---------- 3. 點擊 ----------
        point_data = df[df["level_name"] == "practicepoint"].copy()
        if not point_data.empty:
            user_point = point_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_point.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_point_accuracy"] = {
                "per_user": user_point.to_dict(orient="records"),
                "overall_avg": user_point["accuracy"].mean()
            }

        # ---------- 4. 拖移 ----------
        grab_data = df[df["level_name"] == "practicegrab"].copy()
        if not grab_data.empty:
            user_grab = grab_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_grab.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_drag_accuracy"] = {
                "per_user": user_grab.to_dict(orient="records"),
                "overall_avg": user_grab["accuracy"].mean()
            }

        # ---------- 5. 優惠券九宮格 ----------
        coupon_data = df[df["level_name"].str.lower() == "coupongame"].copy()
        if not coupon_data.empty:
            user_coupon = coupon_data.groupby(["user_id", "grid_index"])["reaction_time"].mean().reset_index()
            coupon_overall = user_coupon.groupby("grid_index")["reaction_time"].mean().reset_index()
            results["coupon_reaction_time"] = {
                "per_user": user_coupon.to_dict(orient="records"),
                "overall_avg": coupon_overall.to_dict(orient="records")
            }

        # ---------- 6. 協作延遲 ----------
        collab_levels = ["eye", "voice", "point", "grab",
                         "eye+voice", "hand+voice", "hand+eye", "hand+eye+voice"]
        collab_data = df[df["level_name"].isin(collab_levels)].copy()
        if not collab_data.empty:
            user_collab = collab_data.groupby(["user_id", "level_name"])["reaction_time"].mean().reset_index()
            collab_overall = user_collab.groupby("level_name")["reaction_time"].mean().reset_index()
            results["collaboration_latency"] = {
                "per_user": user_collab.to_dict(orient="records"),
                "overall_avg": collab_overall.to_dict(orient="records")
            }

        return jsonify(results), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
