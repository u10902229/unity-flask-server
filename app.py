from flask import Flask, request, jsonify
import csv
import os
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
        ws = sh.sheet1                       # 預設第一個分頁
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
        return str(data.get(key, "") or "")

    # ⚠️ 必須和 Google Sheet 表頭完全一致（21 欄）
    row = [
        get("user_id"),
        get("device_type"),
        get("task_type"), get("interaction_type"), get("trial_no"),
        get("target_index"), get("grid_index"),
        get("reaction_time"), get("level_name"),
        get("start_time"), get("end_time"),
        get("gaze_target_x"), get("gaze_target_y"), get("gaze_target_z"),
        get("gaze_x"), get("gaze_y"), get("gaze_z"),
        get("interaction_result"),
        get("process"), get("appear_time"), get("timestamp")
    ]

    print("📤 準備寫入 Google Sheets:", row)
    print("➡️ 欄位數:", len(row))

    # 1️⃣ 本地寫 CSV
    with open(csv_file_path, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)

    # 2️⃣ 同步到 Google Sheets
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdYVojtpX0yVQdn6W4H4KuQ7PlsiGGU"  # 換成你的試算表 ID
        ws = get_sheet(SHEET_ID, "工作表1")
        ws.append_row(row, value_input_option="USER_ENTERED")
        print("✅ 已同步到 Google Sheets")
    except Exception as e:
        import traceback
        print("⚠️ Google Sheets 同步失敗:", e)
        traceback.print_exc()

    return jsonify({"message": "✅ 資料寫入成功"})


# ---------------- 聚合分析 ----------------
@app.route('/aggregate', methods=['GET'])
def aggregate():
    try:
        SHEET_ID = "1C9CJMjEiXeqQYdYVojtpX0yVQdn6W4H4KuQ7PlsiGGU"
        ws = get_sheet(SHEET_ID, "工作表1")

        rows = ws.get_all_values()
        if len(rows) <= 1:
            return jsonify({"message": "Google Sheet is empty"}), 200

        df = pd.DataFrame(rows[1:], columns=rows[0])  # 第一列當表頭
        if df.empty:
            return jsonify({"message": "Google Sheet empty"}), 200

        # 數值型欄位轉換
        df["reaction_time"] = pd.to_numeric(df["reaction_time"], errors="coerce")
        if "interaction_result" in df.columns:
            df["interaction_result"] = pd.to_numeric(df["interaction_result"], errors="coerce")

        results = {}

        # ---------- 1. 眼動 ----------
        eye_data = df[df["level_name"].str.strip().str.lower() == "practicegaze"].copy()
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
                device_eye = eye_data.groupby("device_type")["error"].mean().reset_index()
                results["eye_accuracy"] = {
                    "per_device": device_eye.to_dict(orient="records"),
                    "overall_avg": device_eye["error"].mean()
                }

        # ---------- 2. 語音 ----------
        voice_data = df[df["level_name"] == "practicevoice"].copy()
        if not voice_data.empty:
            device_voice = voice_data.groupby("device_type")["interaction_result"].mean().reset_index()
            device_voice.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["voice_accuracy"] = {
                "per_device": device_voice.to_dict(orient="records"),
                "overall_avg": device_voice["accuracy"].mean()
            }

        # ---------- 3. 點擊 ----------
        point_data = df[df["level_name"] == "practicepoint"].copy()
        if not point_data.empty:
            device_point = point_data.groupby("device_type")["interaction_result"].mean().reset_index()
            device_point.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_point_accuracy"] = {
                "per_device": device_point.to_dict(orient="records"),
                "overall_avg": device_point["accuracy"].mean()
            }

        # ---------- 4. 拖移 ----------
        grab_data = df[df["level_name"] == "practicegrab"].copy()
        if not grab_data.empty:
            device_grab = grab_data.groupby("device_type")["interaction_result"].mean().reset_index()
            device_grab.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_drag_accuracy"] = {
                "per_device": device_grab.to_dict(orient="records"),
                "overall_avg": device_grab["accuracy"].mean()
            }

        # ---------- 5. 優惠券九宮格 ----------
        coupon_data = df[df["level_name"].str.lower() == "coupongame"].copy()
        if not coupon_data.empty:
            grid_map = {
                "1": "1左上", "2": "2中上", "3": "3右上",
                "4": "4左中", "5": "5中心", "6": "6右中",
                "7": "7左下", "8": "8中下", "9": "9右下"
            }
            coupon_data["grid_label"] = coupon_data["grid_index"].map(grid_map)

            user_coupon = coupon_data.groupby(
                ["user_id", "device_type", "grid_index", "grid_label"]
            )["reaction_time"].mean().reset_index()

            coupon_overall = coupon_data.groupby(
                ["grid_index", "grid_label"]
            )["reaction_time"].mean().reset_index()

            results["coupon_reaction_time"] = {
                "per_device": device_coupon.to_dict(orient="records"),
                "overall_avg": coupon_overall.to_dict(orient="records")
            }

        # ---------- 6. 協作延遲 ----------
        collab_levels = ["eye", "voice", "point", "grab",
                         "eye+voice", "hand+voice", "hand+eye", "hand+eye+voice"]
        collab_data = df[df["level_name"].isin(collab_levels)].copy()
        if not collab_data.empty:
            device_collab = collab_data.groupby(["device_type", "level_name"])["reaction_time"].mean().reset_index()
            collab_overall = device_collab.groupby("level_name")["reaction_time"].mean().reset_index()
            results["collaboration_latency"] = {
                "per_device": device_collab.to_dict(orient="records"),
                "overall_avg": collab_overall.to_dict(orient="records")
            }

        return jsonify(results), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
