from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime
import pandas as pd
import numpy as np

app = Flask(__name__)
csv_file_path = "interaction_log.csv"

# 初始化 CSV 檔案
if not os.path.exists(csv_file_path):
    with open(csv_file_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id",
            "task_type", "interaction_type", "trial_no", "target_index", "grid_index",
            "reaction_time", "level_name", "start_time", "end_time",
            "gaze_target_x", "gaze_target_y", "gaze_target_z",
            "gaze_x", "gaze_y", "gaze_z",
            "interaction_result",   # ✅ 加上這個，方便正確率計算
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

    # 將缺少欄位補空值
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

    return jsonify({"message": "✅ 資料寫入成功"})


# ---------------- 聚合分析 ----------------
@app.route('/aggregate', methods=['GET'])
def aggregate():
    try:
        df = pd.read_csv(csv_file_path)
        if df.empty:
            return jsonify({"message": "CSV is empty"}), 200

        # 確保數值型欄位正確
        df["reaction_time"] = pd.to_numeric(df["reaction_time"], errors="coerce")
        if "interaction_result" in df.columns:
            df["interaction_result"] = pd.to_numeric(df["interaction_result"], errors="coerce")

        results = {}

        # ---------- 1. 眼動 (practiceeye) ----------
        eye_data = df[df["level_name"].str.strip().str.lower() == "practicegaze"].copy()
        eye_accuracy = None

        if not eye_data.empty:
            cols = ["gaze_target_x", "gaze_target_y", "gaze_target_z",
                    "gaze_x", "gaze_y", "gaze_z"]

            # 🔹 強制轉成數值
            for c in cols:
                eye_data[c] = pd.to_numeric(eye_data[c], errors="coerce")

            # 🔹 檢查是否全是 NaN
            if eye_data[cols].isna().all().all():
                print("⚠️ 所有 gaze 欄位都是 NaN，無法計算")
            else:
                # 🔹 先把 NaN 填 0 避免整列消失（或用 dropna 視情況）
                eye_data = eye_data.fillna(0)

                # 🔹 計算誤差
                eye_data["error"] = np.sqrt(
                    (eye_data["gaze_target_x"] - eye_data["gaze_x"])**2 +
                    (eye_data["gaze_target_y"] - eye_data["gaze_y"])**2 +
                    (eye_data["gaze_target_z"] - eye_data["gaze_z"])**2
                )

                user_eye = eye_data.groupby("user_id")["error"].mean().reset_index()
                eye_accuracy = {
                    "per_user": user_eye.to_dict(orient="records"),
                    "overall_avg": user_eye["error"].mean()
                }

                results["eye_accuracy"] = eye_accuracy

        # ---------- 2. 語音 (practicevoice) ----------
        voice_data = df[df["level_name"] == "practicevoice"].copy()
        if not voice_data.empty:
            user_voice = voice_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_voice.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["voice_accuracy"] = {
                "per_user": user_voice.to_dict(orient="records"),
                "overall_avg": user_voice["accuracy"].mean()
            }

        # ---------- 3. 點擊 (practicepoint) ----------
        point_data = df[df["level_name"] == "practicepoint"].copy()
        if not point_data.empty:
            user_point = point_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_point.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_point_accuracy"] = {
                "per_user": user_point.to_dict(orient="records"),
                "overall_avg": user_point["accuracy"].mean()
            }

        # ---------- 4. 拖移 (practicegrab) ----------
        grab_data = df[df["level_name"] == "practicegrab"].copy()
        if not grab_data.empty:
            user_grab = grab_data.groupby("user_id")["interaction_result"].mean().reset_index()
            user_grab.rename(columns={"interaction_result": "accuracy"}, inplace=True)
            results["hand_drag_accuracy"] = {
                "per_user": user_grab.to_dict(orient="records"),
                "overall_avg": user_grab["accuracy"].mean()
            }

        # ---------- 5. 優惠券九宮格 (CouponGame) ----------
        coupon_data = df[df["level_name"].str.lower() == "coupongame"].copy()
        if not coupon_data.empty:
            user_coupon = coupon_data.groupby(["user_id", "grid_index"])["reaction_time"].mean().reset_index()
            coupon_overall = user_coupon.groupby("grid_index")["reaction_time"].mean().reset_index()
            results["coupon_reaction_time"] = {
                "per_user": user_coupon.to_dict(orient="records"),
                "overall_avg": coupon_overall.to_dict(orient="records")
            }

        # ---------- 6. 協作延遲 (eye, voice, point, grab...) ----------
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
