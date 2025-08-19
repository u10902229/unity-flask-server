from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime

app = Flask(__name__)
csv_file_path = "interaction_log.csv"

# 初始化 CSV 檔案
if not os.path.exists(csv_file_path):
    with open(csv_file_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "task_type", "interaction_type", "trial_no", "target_index", "grid_index",
            "reaction_time", "level_name", "start_time", "end_time", "gaze_target_x", "gaze_target_y", "gaze_target_z",
            "gaze_x", "gaze_y", "gaze_z", "process", "appear_time", "timestamp"
        ])

@app.route('/')
def index():
    return '✅ Flask 伺服器已運作！'

@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json()
    print("收到資料：", data)

    # 將缺少欄位補空值
    def get(key):
        return data.get(key, "")

    with open(csv_file_path, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            get("task_type"), get("interaction_type"), get("trial_no"), get("target_index"), get("grid_index"),
            get("reaction_time"), get("level_name"), get("start_time"), get("end_time"),
            get("gaze_target_x"), get("gaze_target_y"), get("gaze_target_z"),
            get("gaze_x"), get("gaze_y"), get("gaze_z"),
            get("process"), get("appear_time"), get("timestamp")
        ])

    return jsonify({"message": "✅ 資料寫入成功"})
