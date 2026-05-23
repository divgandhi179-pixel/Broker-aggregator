from adapters.base_adapter import BrokerAdapter

class AlpacaAdapter(BrokerAdapter):

    def __init__(self, api_key:str, secret_key:str):
        self.api_key = api_key
        self.secret_key= secret_key
        self.broker_name = "aplaca"

    async def get_quote(self,symbol: str) -> dict:
        return{
            "symbol":symbol,
            "ltp": 185.40,
            "bid":185.40,
            "ask": 185.60,
            "volume": 987665
        }

    async def place_order(self,symbol: str,qty: int, side: str,order_type:str) -> dict:
        return {
            "broker": self.broker_name,
            "order_id": "ALP789012",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "status": "placed",
        }

    async def get_positions(self) -> list:
        return [
            {"symbol": "AAPL", "qty": 5, "avg_price": 180.00},
            {"symbol": "TSLA", "qty": 3, "avg_price": 250.00},
        ]

    async def get_portfolio(self)-> dict:
        return{
            "broker":self.broker_name,
            "total_value": 185000.00,
            "holdings": [
                {"symbol": "AAPL", "qty": 5, "current_price": 185.50},
                {"symbol": "TSLA", "qty": 3, "current_price": 260.00},
            ],
        }
      