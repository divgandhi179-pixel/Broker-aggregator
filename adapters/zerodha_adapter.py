from adapters.base_adapter import BrokerAdapter


class ZerodhaAdapter(BrokerAdapter):
    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.broker_name = "Zerodha"

    async def get_quote(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "ltp": 2150.00,
            "bid": 2150.00,
            "ask": 2150.00,
            "volume": 123456,
        }

    async def place_order(
        self, symbol: str, qty: int, side: str, order_type: str
    ) -> dict:
        return {
            "broker": self.broker_name,
            "order_id": "ZER123456",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "status": "placed",
        }

    async def get_positions(self) -> list:
        return [
            {"symbol": "INFY", "qty": 10, "avg_price": 1500},
            {"symbol": "TCS", "qty": 10, "avg_price": 3200},
        ]

    async def get_portfolio(self) -> dict:
        return {
            "broker": self.broker_name,
            "total_value": 310000.00,
            "holdings": [
                {"symbol": "INFY", "qty": 10, "current_price": 15000.00},
                {"symbol": "TCS", "qty": 5, "current_price": 1600.00},
            ],
        }
