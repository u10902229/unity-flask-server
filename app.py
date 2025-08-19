from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/upload', methods=['POST'])
def upload_data():
    data = request.json
    print("收到資料：", data)
    return jsonify({'message': '資料接收成功'})

if __name__ == '__main__':
    app.run(debug=True)
