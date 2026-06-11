from adapters.zerodha_adapter import ZerodhaAdapter
from adapters.alpaca_adapter import AlpacaAdapter
from adapters.groww_adapter import GrowwAdapter
from adapters.motilal_oswal_adapter import MotilalOswalAdapter

ADAPTER_MAP = {
    "Zerodha": ZerodhaAdapter,
    "Alpaca": AlpacaAdapter,
    "Groww": GrowwAdapter,
    "Motilal Oswal": MotilalOswalAdapter
}

class BrokerRegistry:
    def __init__(self):
        self.brokers = {}
        
    def register(self, name:str, **credentials):
        if name not in ADAPTER_MAP:
            raise ValueError(f"Unknown Broker: {name}")
        self.brokers[name] = ADAPTER_MAP[name](**credentials)
        print(f"{name} registered successfully")
        
    def unregister(self, name:str):
        if name in self.brokers:
            del self.brokers[name]
            print(f"{name} unregistered successfully")
        
    def get(self, name:str):
        if name not in self.brokers:
            raise ValueError(f"Broker {name} is not registered")
        return self.brokers[name]
    
    def all(self):
        return self.brokers.items() 