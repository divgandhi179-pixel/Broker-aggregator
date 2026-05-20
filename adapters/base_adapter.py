from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    @abstractmethod
    async def get_quotes(self, symbol: str) -> dict:
        """Return price data for a symbol"""
        pass

    @abstractmethod
    async def place_order(
        self, symbol: str, qty: int, side: str, order_type: str
    ) -> dict:
        """Place an order. side = 'BUY' or 'SELL', order_type = 'MARKET' or 'LIMIT'"""
        pass

    @abstractmethod
    async def get_positions(self) -> list:
        """Return list of positions"""
        pass

    @abstractmethod
    async def get_portfolio(self) -> list:
        """Return Total portfolio value and holdings"""
        pass
