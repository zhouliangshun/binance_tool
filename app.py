"""
Binance 交易工具

功能:
1. 允许用户使用 API Key 获取账户信息。
2. 支持 CLI 交互模式，可查看账户信息、执行交易。
3. 提供 Web 界面，允许用户通过浏览器操作。

依赖安装:
- pip install python-binance flask keyring keyrings.cryptfile requests

运行方式:
1. 运行 CLI 模式: python script.py
2. 选择 "启动 Web 服务器" 进入 Web 模式
3. 使用 `python script.py --web` 直接启动 Web 服务器
4. 在 PythonAnywhere 部署时，确保使用 `wsgi.py`
"""

import webbrowser
import argparse
import threading
import keyring
import os
import sys
from binance.client import Client
from flask import Flask, request, jsonify, render_template

KEYRING_SERVICE = "binance_tool"

def parse_args():
    parser = argparse.ArgumentParser(description='Binance Tool CLI')
    parser.add_argument('--web', action='store_true', help='启动 Web 服务器')
    return parser.parse_args()

# 简单的文件存储API密钥的实现，避免使用可能导致内存问题的keyring库
class SimpleFileStorage:
    def __init__(self, service_name):
        self.service_name = service_name
        # 使用更简单的存储路径
        self.storage_dir = os.path.expanduser("~/.config/binance_tool")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.storage_file = os.path.join(self.storage_dir, "credentials.txt")
        # 简单的加密密钥，优先使用环境变量
        self.encryption_key = os.environ.get('BINANCE_TOOL_SECRET', 'default-encryption-key')
    
    def _encrypt(self, text):
        # 简单的XOR加密，生产环境应使用更强的加密
        import base64
        key_bytes = self.encryption_key.encode('utf-8')
        text_bytes = text.encode('utf-8')
        # 循环使用密钥进行XOR操作
        encrypted = bytearray()
        for i in range(len(text_bytes)):
            encrypted.append(text_bytes[i] ^ key_bytes[i % len(key_bytes)])
        return base64.b64encode(encrypted).decode('utf-8')
    
    def _decrypt(self, encrypted_text):
        # 对应的解密方法
        import base64
        try:
            key_bytes = self.encryption_key.encode('utf-8')
            encrypted_bytes = base64.b64decode(encrypted_text)
            # 循环使用密钥进行XOR操作
            decrypted = bytearray()
            for i in range(len(encrypted_bytes)):
                decrypted.append(encrypted_bytes[i] ^ key_bytes[i % len(key_bytes)])
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"解密失败: {str(e)}")
            return None
    
    def set_password(self, service, username, password):
        # 将凭据保存到文件
        try:
            credentials = {}
            # 如果文件已存在，先读取现有凭据
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        try:
                            # 尝试解析现有内容
                            lines = content.split('\n')
                            for line in lines:
                                if line.strip():
                                    parts = line.split(':')
                                    if len(parts) == 3:
                                        svc, user, pwd = parts
                                        credentials[(svc, user)] = pwd
                        except Exception as e:
                            print(f"读取凭据文件失败: {str(e)}")
            
            # 添加或更新凭据
            credentials[(service, username)] = self._encrypt(password)
            
            # 写回文件
            with open(self.storage_file, 'w') as f:
                for (svc, user), pwd in credentials.items():
                    f.write(f"{svc}:{user}:{pwd}\n")
            return True
        except Exception as e:
            print(f"保存凭据失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def get_password(self, service, username):
        # 从文件读取凭据
        try:
            if not os.path.exists(self.storage_file):
                return None
            
            with open(self.storage_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return None
                
                lines = content.split('\n')
                for line in lines:
                    if line.strip():
                        parts = line.split(':')
                        if len(parts) == 3:
                            svc, user, pwd = parts
                            if svc == service and user == username:
                                return self._decrypt(pwd)
            return None
        except Exception as e:
            print(f"读取凭据失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def delete_password(self, service, username):
        # 删除凭据
        try:
            if not os.path.exists(self.storage_file):
                return False
            
            credentials = {}
            with open(self.storage_file, 'r') as f:
                content = f.read().strip()
                if content:
                    lines = content.split('\n')
                    for line in lines:
                        if line.strip():
                            parts = line.split(':')
                            if len(parts) == 3:
                                svc, user, pwd = parts
                                if svc != service or user != username:
                                    credentials[(svc, user)] = pwd
            
            # 写回文件
            with open(self.storage_file, 'w') as f:
                for (svc, user), pwd in credentials.items():
                    f.write(f"{svc}:{user}:{pwd}\n")
            return True
        except Exception as e:
            print(f"删除凭据失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False

# 全局存储实例
_simple_storage = None

def init_keyring():
    try:
        global _simple_storage
        # 检测是否在uwsgi环境下运行
        is_uwsgi = 'uwsgi' in sys.modules
        print(f"环境检测: uwsgi环境={is_uwsgi}, 交互式环境={sys.stdin.isatty()}")
        
        # 在非交互式环境（如uwsgi）下，使用简单文件存储
        if is_uwsgi or not sys.stdin.isatty():
            print("检测到非交互式环境，使用简单文件存储代替keyring")
            try:
                _simple_storage = SimpleFileStorage(KEYRING_SERVICE)
                print("成功初始化简单文件存储")
                return True
            except Exception as e:
                print(f"错误: 无法初始化简单文件存储: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return False
        
        # 根据平台选择合适的keyring后端
        print(f"检测到交互式环境，平台: {sys.platform}")
        if sys.platform.startswith('linux'):
            # 尝试使用 SecretService backend
            try:
                print("尝试使用SecretService作为keyring后端")
                import secretstorage
                keyring.set_keyring(keyring.backends.SecretService.Keyring())
                print("成功设置SecretService作为keyring后端")
                return True
            except Exception as e:
                print(f"警告: 无法初始化SecretService keyring: {str(e)}")
                # 如果 SecretService 不可用，尝试使用文件系统 backend
                try:
                    print("尝试使用文件系统作为备选keyring后端")
                    from keyrings.cryptfile.cryptfile import CryptFileKeyring
                    kr = CryptFileKeyring()
                    # 使用环境变量作为加密密钥，如果未设置则使用默认值
                    kr.keyring_key = os.environ.get('KEYRING_CRYPTFILE_PASSWORD', 'binance-tool-default-key')
                    keyring.set_keyring(kr)
                    print("成功设置文件系统作为备选keyring后端")
                    return True
                except Exception as e:
                    print(f"错误: 无法初始化备选keyring: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return False
        elif sys.platform == 'darwin':
            print("在macOS上使用系统keychain")
            return True  # macOS默认使用系统keychain
        elif sys.platform == 'win32':
            print("在Windows上使用系统凭据管理器")
            return True  # Windows默认使用凭据管理器
        else:
            # 其他平台尝试使用文件系统backend
            try:
                print(f"未知平台{sys.platform}，尝试使用文件系统作为keyring后端")
                from keyrings.cryptfile.cryptfile import CryptFileKeyring
                kr = CryptFileKeyring()
                kr.keyring_key = os.environ.get('KEYRING_CRYPTFILE_PASSWORD', 'binance-tool-default-key')
                keyring.set_keyring(kr)
                print("成功设置文件系统作为keyring后端")
                return True
            except Exception as e:
                print(f"错误: 无法初始化keyring: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return False
    except Exception as e:
        print(f"错误: keyring初始化过程中发生异常: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False
    return True

def get_api_key():
    if not init_keyring():
        print("无法初始化凭据存储系统，返回空API密钥")
        return None, None
    try:
        # 检查是否使用简单文件存储
        global _simple_storage
        if _simple_storage is not None:
            # 使用简单文件存储
            api_key = _simple_storage.get_password(KEYRING_SERVICE, "api_key")
            api_secret = _simple_storage.get_password(KEYRING_SERVICE, "api_secret")
        else:
            # 使用keyring
            api_key = keyring.get_password(KEYRING_SERVICE, "api_key")
            api_secret = keyring.get_password(KEYRING_SERVICE, "api_secret")
        
        if not api_key or not api_secret:
            print("未找到保存的API密钥")
        return api_key, api_secret
    except Exception as e:
        print(f"获取 API Key 失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None, None

def set_api_key(api_key, api_secret):
    if not init_keyring():
        print("无法初始化凭据存储系统，无法保存API密钥")
        return "无法初始化凭据存储系统"
    try:
        # 先验证API密钥是否有效
        client = Client(api_key, api_secret)
        client.get_account()
        
        # API密钥有效，尝试保存
        try:
            # 检查是否使用简单文件存储
            global _simple_storage
            if _simple_storage is not None:
                # 使用简单文件存储
                _simple_storage.set_password(KEYRING_SERVICE, "api_key", api_key)
                _simple_storage.set_password(KEYRING_SERVICE, "api_secret", api_secret)
            else:
                # 使用keyring
                keyring.set_password(KEYRING_SERVICE, "api_key", api_key)
                keyring.set_password(KEYRING_SERVICE, "api_secret", api_secret)
            
            print("API密钥保存成功")
            return True
        except Exception as e:
            error_msg = f"API Key 验证成功，但无法保存: {str(e)}"
            print(error_msg)
            import traceback
            print(traceback.format_exc())
            return error_msg
    except Exception as e:
        error_msg = f"API Key 验证失败: {str(e)}"
        print(error_msg)
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
            # 检查是否使用简单文件存储
            global _simple_storage
            if _simple_storage is not None:
                # 使用简单文件存储删除密钥
                _simple_storage.delete_password(KEYRING_SERVICE, "api_key")
                _simple_storage.delete_password(KEYRING_SERVICE, "api_secret")
            else:
                # 使用keyring删除密钥
                keyring.delete_password(KEYRING_SERVICE, "api_key")
                keyring.delete_password(KEYRING_SERVICE, "api_secret")
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
