"""
Binance 交易工具

功能:
1. 允许用户使用 API Key 获取账户信息。
2. 支持 CLI 交互模式，可查看账户信息、执行交易。
3. 提供 Web 界面，允许用户通过浏览器操作。

依赖安装:
- pip install python-binance flask keyring requests

运行方式:
1. 运行 CLI 模式: python script.py
2. 选择 "启动 Web 服务器" 进入 Web 模式
3. 使用 `python script.py --web` 直接启动 Web 服务器
4. 在 PythonAnywhere 部署时，确保使用 `wsgi.py`
"""

import os
import json
import webbrowser
import argparse
import threading
from binance.client import Client
from flask import Flask, request, jsonify, render_template

CONFIG_FILE = "config.json"

def parse_args():
    parser = argparse.ArgumentParser(description='Binance Tool CLI')
    parser.add_argument('--web', action='store_true', help='启动 Web 服务器')
    return parser.parse_args()

def get_api_key():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data.get("api_key"), data.get("api_secret")
    return None, None

def set_api_key(api_key, api_secret):
    client = Client(api_key, api_secret)
    try:
        client.get_account()
        with open(CONFIG_FILE, "w") as f:
            json.dump({"api_key": api_key, "api_secret": api_secret}, f)
        return True
    except Exception as e:
        return str(e)

def get_account_info(client):
    try:
        account_info = client.get_account()
        balances = account_info['balances']
        total_balance = sum(float(b['free']) + float(b['locked']) for b in balances)
        return {"account_type": account_info['accountType'], "total_balance": total_balance, "nickname": account_info.get('nickname', '未知')}
    except Exception as e:
        return str(e)

def trade(client, trade_type, symbol, quantity):
    try:
        if trade_type == "BUY":
            order = client.order_market_buy(symbol=symbol, quantity=quantity)
        else:
            order = client.order_market_sell(symbol=symbol, quantity=quantity)
        return order
    except Exception as e:
        return str(e)

def cli_menu():
    while True:
        api_key, api_secret = get_api_key()
        if not api_key or not api_secret:
            api_key = input("请输入您的 Binance API Key: ")
            api_secret = input("请输入您的 Binance API Secret: ")
            result = set_api_key(api_key, api_secret)
            if result is not True:
                print(f"API Key 无效: {result}")
                continue
        
        client = Client(api_key, api_secret)
        account_info = get_account_info(client)
        if isinstance(account_info, str):
            print(f"无法获取账户信息: {account_info}")
            os.remove(CONFIG_FILE)
            continue
        
        print(f"\n账户昵称: {account_info['nickname']}  总余额: {account_info['total_balance']}")
        print("\n1. 查看账户信息\n2. 买入\n3. 卖出\n4. 启动 Web 服务器\n5. 退出")
        choice = input("请选择操作: ")
        if choice == "1":
            print(account_info)
        elif choice == "2":
            symbol = input("请输入买入币种（如 BTCUSDT）：").upper()
            quantity = input("请输入买入数量：")
            result = trade(client, "BUY", symbol, quantity)
            print(result)
        elif choice == "3":
            symbol = input("请输入卖出币种（如 BTCUSDT）：").upper()
            quantity = input("请输入卖出数量：")
            result = trade(client, "SELL", symbol, quantity)
            print(result)
        elif choice == "4":
            start_web_server()
            webbrowser.open("http://127.0.0.1:5000/")
        elif choice == "5":
            break
        else:
            print("无效输入，请重新选择。")

def start_web_server():
    app.run(host='0.0.0.0', port=5000)

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/set_api', methods=['POST'])
def set_api():
    data = request.json
    api_key = data.get("api_key")
    api_secret = data.get("api_secret")
    result = set_api_key(api_key, api_secret)
    if result is True:
        return jsonify({"message": "API Key 设置成功"}), 200
    return jsonify({"message": f"API Key 无效: {result}"}), 400

@app.route('/account', methods=['GET'])
def account():
    api_key, api_secret = get_api_key()
    if not api_key or not api_secret:
        return jsonify({"message": "请先设置 API Key"}), 400
    client = Client(api_key, api_secret)
    account_info = get_account_info(client)
    if isinstance(account_info, dict):
        return jsonify(account_info)
    return jsonify({"message": f"获取账户信息失败: {account_info}"}), 400

@app.route('/trade', methods=['POST'])
def trade_route():
    api_key, api_secret = get_api_key()
    if not api_key or not api_secret:
        return jsonify({"message": "请先设置 API Key"}), 400
    client = Client(api_key, api_secret)
    data = request.json
    trade_type = data.get("trade_type")
    symbol = data.get("symbol").upper()
    quantity = data.get("quantity")
    result = trade(client, trade_type, symbol, quantity)
    return jsonify(result)

if __name__ == "__main__":
    args = parse_args()
    if args.web:
        start_web_server()
    else:
        cli_menu()
