import ccxt
import requests
import time
import threading
import os
from typing import Dict, List, Optional, Any, Callable

# 获取系统代理设置
def get_system_proxies() -> Dict[str, str]:
    """获取系统代理设置
    
    从环境变量中获取HTTP和HTTPS代理设置
    
    Returns:
        包含代理设置的字典，如果没有设置则返回空字典
    """
    proxies = {}
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    
    if http_proxy:
        proxies['http'] = http_proxy
    if https_proxy:
        proxies['https'] = https_proxy
    
    return proxies

class ExchangeAPI:
    """交易所API基类，定义通用接口"""
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.last_update_time = 0
        self.prices: Dict[str, float] = {}
        self._update_thread = None
        self._stop_thread = False
    
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """获取指定交易对的最新价格"""
        raise NotImplementedError("子类必须实现此方法")
    
    def get_all_tickers(self) -> Dict[str, float]:
        """获取所有交易对的最新价格"""
        raise NotImplementedError("子类必须实现此方法")
    
    def start_price_update(self, symbols: List[str], callback: Optional[Callable] = None, interval: int = 5):
        """启动价格更新线程"""
        if self._update_thread and self._update_thread.is_alive():
            return
        
        self._stop_thread = False
        self._update_thread = threading.Thread(
            target=self._price_update_loop,
            args=(symbols, callback, interval),
            daemon=True
        )
        self._update_thread.start()
    
    def stop_price_update(self):
        """停止价格更新线程"""
        self._stop_thread = True
        if self._update_thread:
            self._update_thread.join(timeout=1.0)
    
    def _price_update_loop(self, symbols: List[str], callback: Optional[Callable], interval: int):
        """价格更新循环"""
        while not self._stop_thread:
            try:
                self.prices = self._fetch_prices(symbols)
                self.last_update_time = time.time()
                if callback:
                    callback(self.prices)
            except Exception as e:
                print(f"获取价格时出错: {str(e)}")
            time.sleep(interval)
    
    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """获取指定交易对的价格"""
        raise NotImplementedError("子类必须实现此方法")


class BinanceAPI(ExchangeAPI):
    """币安API实现"""
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        super().__init__(api_key, api_secret)
        
        # 获取系统代理设置
        proxies = get_system_proxies()
        
        # 创建交易所配置
        exchange_config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        }
        
        # 如果存在代理设置，添加到配置中
        if proxies:
            exchange_config['proxies'] = proxies
            print(f"Binance: 使用系统代理设置: {proxies}")
        
        self.exchange = ccxt.binance(exchange_config)
    
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            print(f"获取{symbol}价格失败: {str(e)}")
            return None
    
    def get_all_tickers(self) -> Dict[str, float]:
        try:
            tickers = self.exchange.fetch_tickers()
            return {symbol: ticker['last'] for symbol, ticker in tickers.items()}
        except Exception as e:
            print(f"获取所有价格失败: {str(e)}")
            return {}
    
    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        result = {}
        try:
            # 如果symbols为空，获取所有交易对价格
            if not symbols:
                tickers = self.exchange.fetch_tickers()
                return {symbol: ticker['last'] for symbol, ticker in tickers.items()}
            
            # 否则只获取指定交易对价格
            for symbol in symbols:
                ticker = self.exchange.fetch_ticker(symbol)
                result[symbol] = ticker['last']
        except Exception as e:
            print(f"获取价格失败: {str(e)}")
        return result


class OKCoinAPI(ExchangeAPI):
    """OKCoin Japan API实现 (使用官方API，显示JPY价格)"""
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        super().__init__(api_key, api_secret)
        # 使用OKCoin Japan官方API，显示JPY价格
        
        # 获取系统代理设置
        proxies = get_system_proxies()
        
        self.base_url = 'https://www.okcoin.jp/api/spot/v3'
        self.session = requests.Session()
        self.session.proxies.update(proxies)
        
        if api_key and api_secret:
            self.api_key = api_key
            self.api_secret = api_secret
            print("使用提供的API密钥进行认证")
        else:
            print("未提供API密钥，将只能访问公开市场数据")
    
    def _convert_symbol(self, symbol: str) -> str:
        """将Binance格式的交易对转换为OKCoin Japan格式（JPY）"""
        # 如果已经是OKCoin格式（包含/），则直接返回
        if '-JPY' in symbol:
            return symbol
        # 否则尝试转换
        return f"{symbol[:-4]}-JPY"
    
    def _reverse_convert_symbol(self, symbol: str) -> str:
        """将OKCoin Japan格式的交易对转换为Binance格式"""
        # 如果已经是Binance格式（不包含/），则直接返回
        if 'USDT' not in symbol:
            return symbol
        # 否则尝试转换
        return f"{symbol[:-3]}USDT"
    
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        try:
            okcoin_symbol = self._convert_symbol(symbol)
            response = self.session.get(f"{self.base_url}/instruments/{okcoin_symbol}/ticker")
            response.raise_for_status()
            ticker = response.json()
            return float(ticker['last'])
        except Exception as e:
            print(f"获取{symbol}价格失败: {str(e)}")
            return None
    
    def get_all_tickers(self) -> Dict[str, float]:
        try:
            response = self.session.get(f"{self.base_url}/instruments/ticker")
            response.raise_for_status()
            tickers = response.json()
            result = {}
            for ticker in tickers:
                binance_symbol = self._reverse_convert_symbol(ticker['instrument_id'])
                result[binance_symbol] = float(ticker['last'])
            return result
        except Exception as e:
            print(f"获取所有价格失败: {str(e)}")
            return {}
    
    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        result = {}
        try:
            if not symbols:
                return self.get_all_tickers()
            
            for symbol in symbols:
                price = self.get_ticker_price(symbol)
                if price is not None:
                    result[symbol] = price
        except Exception as e:
            print(f"获取价格过程中发生错误: {str(e)}")
            import traceback
            print(traceback.format_exc())
        
        return result

# 工厂函数，根据交易所名称创建相应的API实例
def create_exchange_api(exchange_name: str, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> ExchangeAPI:
    """创建交易所API实例
    
    Args:
        exchange_name: 交易所名称，支持 'binance', 'okcoin'
        api_key: API Key
        api_secret: API Secret
    
    Returns:
        ExchangeAPI实例
    """
    exchange_name = exchange_name.lower()
    if exchange_name == 'binance':
        return BinanceAPI(api_key, api_secret)
    elif exchange_name == 'okcoin':
        return OKCoinAPI(api_key, api_secret)
    else:
        raise ValueError(f"不支持的交易所: {exchange_name}")