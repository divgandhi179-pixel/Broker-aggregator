from backend.adapters.zerodha_adapter import ZerodhaAdapter
from backend.adapters.alpaca_adapter import AlpacaAdapter
from backend.adapters.groww_adapter import GrowwAdapter
from backend.adapters.motilal_oswal_adapter import MotilalOswalAdapter


ADAPTER_MAP = {
    "Zerodha": ZerodhaAdapter,
    "Alpaca": AlpacaAdapter,
    "Groww": GrowwAdapter,
    "Motilal Oswal": MotilalOswalAdapter
}

class BrokerRegistry:
    def __init__(self):
        self.brokers = {} # key: (user_id, name)
        
    def register(self, user_id: int, name: str, **credentials):
        if name not in ADAPTER_MAP:
            raise ValueError(f"Unknown Broker: {name}")
        self.brokers[(user_id, name)] = ADAPTER_MAP[name](**credentials)
        print(f"{name} registered successfully for user {user_id}")
        
    def unregister(self, user_id: int, name: str):
        key = (user_id, name)
        if key in self.brokers:
            del self.brokers[key]
            print(f"{name} unregistered successfully for user {user_id}")
        
    def get(self, user_id: int, name: str):
        key = (user_id, name)
        if key not in self.brokers:
            raise ValueError(f"Broker {name} is not registered")
        return self.brokers[key]
    
    def all_for_user(self, user_id: int):
        return [(name, broker) for (uid, name), broker in self.brokers.items() if uid == user_id]
 