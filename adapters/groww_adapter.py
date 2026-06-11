import time
import random
from adapters.base_adapter import BrokerAdapter


class GrowwAdapter(BrokerAdapter):

    def __init__(self, api_key: str, client_id: str):
        self.api_key = api_key
        self.client_id = client_id
        self.broker_name = "Groww"
        # Initial mock holdings
        self.holdings = [
            {"symbol": "RELIANCE", "qty": 8, "current_price": 2400.00},
            {"symbol": "HDFCBANK", "qty": 12, "current_price": 1600.00},
        ]

    async def get_quote(self, symbol: str) -> dict:
        symbol = symbol.upper()
        prices = {
            "INFY": 1500.00,
            "TCS": 3200.00,
            "RELIANCE": 2400.00,
            "HDFCBANK": 1600.00,
            "TATAMOTORS": 950.00
        }
        ltp = prices.get(symbol, 400.00)
        
        # Add tiny random fluctuation (+/- 0.2%)
        ltp = round(ltp * (1 + random.uniform(-0.002, 0.002)), 2)
        
        return {
            "symbol": symbol,
            "ltp": ltp,
            "bid": round(ltp - 1.00, 2),
            "ask": round(ltp + 1.00, 2),
            "volume": random.randint(150000, 600000),
        }

    async def place_order(
        self, symbol: str, qty: int, side: str, order_type: str
    ) -> dict:
        symbol = symbol.upper()
        side = side.upper()
        
        if side not in ["BUY", "SELL"]:
            raise ValueError("Side must be BUY or SELL")
            
        quote = await self.get_quote(symbol)
        price = quote["ltp"]
        
        # Find if holding exists
        holding = next((h for h in self.holdings if h["symbol"] == symbol), None)
        
        if side == "BUY":
            if holding:
                holding["qty"] += qty
                holding["current_price"] = price
            else:
                self.holdings.append({
                    "symbol": symbol,
                    "qty": qty,
                    "current_price": price
                })
        elif side == "SELL":
            if not holding:
                raise ValueError(f"No holding found for {symbol} to sell.")
            if holding["qty"] < qty:
                raise ValueError(f"Insufficient quantity. Holding {holding['qty']} but trying to sell {qty}.")
            
            holding["qty"] -= qty
            if holding["qty"] == 0:
                self.holdings.remove(holding)
                
        return {
            "broker": self.broker_name,
            "order_id": f"GRW{int(time.time() * 1000) % 1000000:06d}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "status": "placed",
        }

    async def get_positions(self) -> list:
        # Map holdings to positions (showing simulated average cost 4% below current price)
        return [
            {
                "symbol": h["symbol"],
                "qty": h["qty"],
                "avg_price": round(h["current_price"] * 0.96, 2)
            }
            for h in self.holdings
        ]

    async def get_portfolio(self) -> dict:
        total_value = sum(h["qty"] * h["current_price"] for h in self.holdings)
        return {
            "broker": self.broker_name,
            "total_value": round(total_value, 2),
            "holdings": self.holdings,
        }
