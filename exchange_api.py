import ccxt
import requests
import time
import threading
from typing import Dict, List, Optional, Any, Callable

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
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })
    
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
    """OKCoin API实现 (使用OKX API)"""
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        super().__init__(api_key, api_secret)
        # 使用okx交易所代替okcoin，因为OKCoin已被OKX收购
        try:
            print("尝试使用OKX API代替OKCoin API")
            # 创建交易所配置，只有在提供了API密钥时才添加认证信息
            exchange_config = {
                'enableRateLimit': True,
                'timeout': 30000,  # 增加超时时间
                'verbose': False,   # 关闭详细日志，减少输出
            }
            
            # 只有在提供了有效的API密钥和密钥时才添加认证信息
            if api_key and api_secret:
                exchange_config['apiKey'] = api_key
                exchange_config['secret'] = api_secret
                print("使用提供的API密钥进行认证")
            else:
                print("未提供API密钥，将只能访问公开市场数据")
                
            self.exchange = ccxt.okx(exchange_config)
            print("成功初始化OKX交易所API")
        except Exception as e:
            print(f"初始化OKX交易所API失败: {str(e)}，尝试使用原始OKCoin API")
            # 创建交易所配置，只有在提供了API密钥时才添加认证信息
            exchange_config = {
                'enableRateLimit': True,
                'timeout': 30000,  # 增加超时时间
                'verbose': False,   # 关闭详细日志，减少输出
            }
            
            # 只有在提供了有效的API密钥和密钥时才添加认证信息
            if api_key and api_secret:
                exchange_config['apiKey'] = api_key
                exchange_config['secret'] = api_secret
            
            self.exchange = ccxt.okcoin(exchange_config)
        # OKCoin的交易对格式可能与Binance不同，需要映射
        self.symbol_map = {
            # Binance格式 -> OKCoin格式
            'BTCUSDT': 'BTC/USDT',
            'ETHUSDT': 'ETH/USDT',
            'LTCUSDT': 'LTC/USDT',
            'XRPUSDT': 'XRP/USDT',
            'ETCUSDT': 'ETC/USDT',
            'BCHUSDT': 'BCH/USDT',
            'EOSUSDT': 'EOS/USDT',
            'BSVUSDT': 'BSV/USDT',
            'TRXUSDT': 'TRX/USDT',
            'ADAUSDT': 'ADA/USDT',
            'DOGEUSDT': 'DOGE/USDT',
            'SOLUSDT': 'SOL/USDT',
            'DOTUSDT': 'DOT/USDT',
            'MATICUSDT': 'MATIC/USDT',
            'BNBUSDT': 'BNB/USDT',
        }
        # 反向映射，用于将OKCoin格式转换回Binance格式
        self.reverse_symbol_map = {v: k for k, v in self.symbol_map.items()}
    
    def _convert_symbol(self, symbol: str) -> str:
        """将Binance格式的交易对转换为OKCoin格式"""
        # 如果已经是OKCoin格式（包含/），则直接返回
        if '/' in symbol:
            return symbol
        # 否则尝试转换
        return self.symbol_map.get(symbol, f"{symbol[:-4]}/{symbol[-4:]}")
    
    def _reverse_convert_symbol(self, symbol: str) -> str:
        """将OKCoin格式的交易对转换为Binance格式"""
        # 如果已经是Binance格式（不包含/），则直接返回
        if '/' not in symbol:
            return symbol
        # 否则尝试转换
        return self.reverse_symbol_map.get(symbol, symbol.replace('/', ''))
    
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        try:
            okcoin_symbol = self._convert_symbol(symbol)
            ticker = self.exchange.fetch_ticker(okcoin_symbol)
            return ticker['last']
        except Exception as e:
            print(f"获取{symbol}价格失败: {str(e)}")
            # 不再返回模拟价格
            return None
    
    def get_all_tickers(self) -> Dict[str, float]:
        try:
            tickers = self.exchange.fetch_tickers()
            # 将OKCoin格式的交易对转换回Binance格式
            result = {}
            for symbol, ticker in tickers.items():
                binance_symbol = self._reverse_convert_symbol(symbol)
                result[binance_symbol] = ticker['last']
            return result
        except Exception as e:
            print(f"获取所有价格失败: {str(e)}")
            # 不再返回模拟价格，直接返回空字典
            return {}
    
    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        result = {}
        try:
            # 如果symbols为空，获取所有交易对价格
            if not symbols:
                print(f"OKCoin: 尝试获取所有交易对价格")
                try:
                    # 尝试使用fetch_tickers获取所有价格
                    tickers = self.exchange.fetch_tickers()
                    print(f"OKCoin: 成功获取所有交易对，数量: {len(tickers)}")
                    for symbol, ticker in tickers.items():
                        try:
                            binance_symbol = self._reverse_convert_symbol(symbol)
                            result[binance_symbol] = ticker['last']
                        except Exception as e:
                            print(f"OKCoin: 转换交易对 {symbol} 失败: {str(e)}")
                    return result
                except Exception as e:
                    print(f"OKCoin: 获取所有交易对价格失败: {str(e)}")
                    # 尝试获取常见交易对价格作为备选
                    print("OKCoin: 尝试获取常见交易对价格作为备选")
                    symbols = list(self.symbol_map.keys())
            
            # 将Binance格式的交易对转换为OKCoin格式
            print(f"OKCoin: 尝试获取指定交易对价格，数量: {len(symbols)}")
            
            # 批量获取价格，减少API调用次数
            try:
                # 转换所有交易对格式
                okcoin_symbols = [self._convert_symbol(s) for s in symbols]
                
                # 使用markets信息验证交易对是否存在
                markets = self.exchange.load_markets()
                valid_symbols = []
                symbol_map = {}
                
                for i, okcoin_symbol in enumerate(okcoin_symbols):
                    if okcoin_symbol in markets:
                        valid_symbols.append(okcoin_symbol)
                        symbol_map[okcoin_symbol] = symbols[i]
                    else:
                        print(f"OKCoin: 交易对 {okcoin_symbol} 在交易所中不存在")
                
                if valid_symbols:
                    # 批量获取价格
                    tickers = self.exchange.fetch_tickers(valid_symbols)
                    for okcoin_symbol, ticker in tickers.items():
                        binance_symbol = symbol_map.get(okcoin_symbol)
                        if binance_symbol:
                            result[binance_symbol] = ticker['last']
                            print(f"OKCoin: 成功获取 {binance_symbol} 价格: {ticker['last']}")
                
                # 如果没有获取到任何价格，尝试单个获取
                if not result and symbols:
                    print("OKCoin: 批量获取失败，尝试单个获取价格")
                    for i, symbol in enumerate(symbols):
                        try:
                            okcoin_symbol = self._convert_symbol(symbol)
                            ticker = self.exchange.fetch_ticker(okcoin_symbol)
                            result[symbol] = ticker['last']
                            print(f"OKCoin: 成功获取 {symbol} 价格: {ticker['last']}")
                        except Exception as e:
                            print(f"OKCoin: 获取 {symbol}({okcoin_symbol}) 价格失败: {str(e)}")
            except Exception as e:
                print(f"OKCoin: 批量获取价格失败: {str(e)}")
                # 回退到单个获取
                for symbol in symbols:
                    try:
                        okcoin_symbol = self._convert_symbol(symbol)
                        ticker = self.exchange.fetch_ticker(okcoin_symbol)
                        result[symbol] = ticker['last']
                        print(f"OKCoin: 成功获取 {symbol} 价格: {ticker['last']}")
                    except Exception as e:
                        print(f"OKCoin: 获取 {symbol}({okcoin_symbol}) 价格失败: {str(e)}")
        except Exception as e:
            print(f"OKCoin: 获取价格过程中发生错误: {str(e)}")
            import traceback
            print(traceback.format_exc())
        
        # 如果没有获取到任何价格，返回空结果
        if not result and symbols:
            print("OKCoin: 警告 - 未能获取任何价格，返回空结果")
        
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