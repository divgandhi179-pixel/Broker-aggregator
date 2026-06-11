import os
import json
import asyncio
import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from backend.broker_registry import BrokerRegistry

app = FastAPI(title="Broker Aggregator API")

# Registry instance
registry = BrokerRegistry()

# Paths for persistence (Vercel has read-only filesystem, use /tmp if on Vercel)
if os.environ.get("VERCEL"):
    BROKERS_FILE = "/tmp/registered_brokers.json"
    HISTORY_FILE = "/tmp/order_history.json"
    IPO_APPLICATIONS_FILE = "/tmp/ipo_applications.json"
else:
    os.makedirs("data", exist_ok=True)
    BROKERS_FILE = "data/registered_brokers.json"
    HISTORY_FILE = "data/order_history.json"
    IPO_APPLICATIONS_FILE = "data/ipo_applications.json"


class BrokerConfig(BaseModel):
    broker: str
    credentials: Dict[str, Any]

class OrderRequest(BaseModel):
    broker: str
    symbol: str
    qty: int
    side: str
    order_type: str = "MARKET"

class IPOApplyRequest(BaseModel):
    broker: str
    ipo_symbol: str
    lots: int
    bid_price: float
    upi_id: str

# Ensure persistence files exist
def init_files():
    if not os.path.exists(BROKERS_FILE):
        with open(BROKERS_FILE, "w") as f:
            json.dump({}, f)
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            json.dump([], f)
    if not os.path.exists(IPO_APPLICATIONS_FILE):
        with open(IPO_APPLICATIONS_FILE, "w") as f:
            json.dump([], f)

def load_registered_brokers():
    try:
        with open(BROKERS_FILE, "r") as f:
            data = json.load(f)
            for name, creds in data.items():
                try:
                    registry.register(name, **creds)
                except Exception as e:
                    print(f"Failed to register broker {name} from config: {e}")
    except Exception as e:
        print(f"Error loading registered brokers: {e}")

def save_broker_config(name: str, creds: Dict[str, Any]):
    try:
        with open(BROKERS_FILE, "r") as f:
            data = json.load(f)
        data[name] = creds
        with open(BROKERS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving broker config: {e}")

def remove_broker_config(name: str):
    try:
        with open(BROKERS_FILE, "r") as f:
            data = json.load(f)
        if name in data:
            del data[name]
        with open(BROKERS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error removing broker config: {e}")

def load_order_history() -> List[Dict[str, Any]]:
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading order history: {e}")
        return []

def add_order_to_history(order: Dict[str, Any]):
    try:
        history = load_order_history()
        history.insert(0, order) # Add to beginning (latest first)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Error adding order to history: {e}")

# Initialize files immediately on load
init_files()

# Initialize and load config on startup
@app.on_event("startup")
async def startup_event():
    load_registered_brokers()
    asyncio.create_task(broadcast_updates_loop())

@app.get("/api/brokers")
async def get_brokers():
    # Return list of all available brokers and which ones are currently active
    supported = ["Zerodha", "Alpaca", "Groww", "Motilal Oswal"]
    active = [name for name, _ in registry.all()]
    return {
        "supported": supported,
        "active": active
    }

@app.post("/api/brokers")
async def register_broker(config: BrokerConfig):
    # Validate broker name
    if config.broker not in ["Zerodha", "Alpaca", "Groww", "Motilal Oswal"]:
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {config.broker}")
    
    try:
        registry.register(config.broker, **config.credentials)
        save_broker_config(config.broker, config.credentials)
        return {"status": "success", "message": f"{config.broker} broker registered and persisted."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/brokers/{name}")
async def unregister_broker(name: str):
    try:
        registry.unregister(name)
        remove_broker_config(name)
        return {"status": "success", "message": f"{name} broker disconnected."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/portfolios")
async def get_all_portfolios():
    # Gather portfolios from active brokers concurrently
    active_brokers = list(registry.all())
    if not active_brokers:
        return {"portfolios": [], "summary": {"total_value": 0, "active_count": 0}}
        
    tasks = []
    for name, broker in active_brokers:
        tasks.append(broker.get_portfolio())
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    portfolios_data = []
    total_aggregate_value = 0.0
    
    for i, res in enumerate(results):
        broker_name = active_brokers[i][0]
        if isinstance(res, Exception):
            portfolios_data.append({
                "broker": broker_name,
                "error": str(res),
                "total_value": 0,
                "holdings": []
            })
        else:
            portfolios_data.append(res)
            # Standardize total_value as float
            try:
                total_aggregate_value += float(res.get("total_value", 0.0))
            except:
                pass
            
    return {
        "portfolios": portfolios_data,
        "summary": {
            "total_value": round(total_aggregate_value, 2),
            "active_count": len(active_brokers)
        }
    }

@app.get("/api/positions")
async def get_all_positions():
    # Gather positions from active brokers concurrently
    active_brokers = list(registry.all())
    if not active_brokers:
        return []
        
    tasks = []
    for name, broker in active_brokers:
        tasks.append(broker.get_positions())
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    positions_data = []
    for i, res in enumerate(results):
        broker_name = active_brokers[i][0]
        if not isinstance(res, Exception):
            for pos in res:
                pos_copy = pos.copy()
                pos_copy["broker"] = broker_name
                positions_data.append(pos_copy)
                
    return positions_data

@app.get("/api/quote/{broker_name}/{symbol}")
async def get_broker_quote(broker_name: str, symbol: str):
    try:
        broker = registry.get(broker_name)
        quote = await broker.get_quote(symbol)
        return quote
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/orders")
async def place_order(order: OrderRequest):
    try:
        broker = registry.get(order.broker)
        # Execute order on the broker (updates its internal holdings)
        res = await broker.place_order(
            symbol=order.symbol,
            qty=order.qty,
            side=order.side,
            order_type=order.order_type
        )
        
        # Add details to order structure for logs
        order_log = res.copy()
        order_log["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Fetch quote to record execution price
        quote = await broker.get_quote(order.symbol)
        order_log["execution_price"] = quote["ltp"]
        
        add_order_to_history(order_log)
        return order_log
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/history")
async def get_history():
    return load_order_history()


# Mock IPOs Database
MOCK_IPOS = [
    {
        "company_name": "Ola Electric Mobility Ltd",
        "symbol": "OLA",
        "price_range": "₹72 - ₹76",
        "min_price": 72.0,
        "max_price": 76.0,
        "lot_size": 195,
        "open_date": "2026-06-11",
        "close_date": "2026-06-15",
        "status": "OPEN",
        "subscribed": "1.8x",
        "currency": "₹"
    },
    {
        "company_name": "Swiggy Limited",
        "symbol": "SWIGGY",
        "price_range": "₹371 - ₹390",
        "min_price": 371.0,
        "max_price": 390.0,
        "lot_size": 38,
        "open_date": "2026-06-10",
        "close_date": "2026-06-14",
        "status": "OPEN",
        "subscribed": "4.2x",
        "currency": "₹"
    },
    {
        "company_name": "Hyundai Motor India Ltd",
        "symbol": "HYUNDAI",
        "price_range": "₹1860 - ₹1960",
        "min_price": 1860.0,
        "max_price": 1960.0,
        "lot_size": 7,
        "open_date": "2026-06-20",
        "close_date": "2026-06-23",
        "status": "UPCOMING",
        "subscribed": "0.0x",
        "currency": "₹"
    },
    {
        "company_name": "Brainbees Solutions Ltd (FirstCry)",
        "symbol": "FIRSTCRY",
        "price_range": "₹440 - ₹465",
        "min_price": 440.0,
        "max_price": 465.0,
        "lot_size": 32,
        "open_date": "2026-06-01",
        "close_date": "2026-06-04",
        "status": "CLOSED",
        "subscribed": "12.4x",
        "currency": "₹"
    }
]

def load_ipo_applications() -> List[Dict[str, Any]]:
    try:
        with open(IPO_APPLICATIONS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading IPO applications: {e}")
        return []

def save_ipo_applications(apps: List[Dict[str, Any]]):
    try:
        with open(IPO_APPLICATIONS_FILE, "w") as f:
            json.dump(apps, f, indent=4)
    except Exception as e:
        print(f"Error saving IPO applications: {e}")

@app.get("/api/ipos")
async def get_ipos():
    return MOCK_IPOS

@app.get("/api/ipos/applications")
async def get_ipo_applications():
    return load_ipo_applications()

@app.post("/api/ipos/apply")
async def apply_ipo(req: IPOApplyRequest):
    # Validate broker is connected
    try:
        broker = registry.get(req.broker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Broker {req.broker} is not connected. Connect the broker first.")

    # Find the IPO details
    ipo = next((i for i in MOCK_IPOS if i["symbol"] == req.ipo_symbol), None)
    if not ipo:
        raise HTTPException(status_code=400, detail=f"IPO {req.ipo_symbol} not found.")

    if ipo["status"] != "OPEN":
        raise HTTPException(status_code=400, detail=f"IPO {req.ipo_symbol} is not open for bidding.")

    # Validate price is within range
    if req.bid_price < ipo["min_price"] or req.bid_price > ipo["max_price"]:
        raise HTTPException(status_code=400, detail=f"Bid price must be between {ipo['price_range']}.")

    # Calculate bid amount
    shares = req.lots * ipo["lot_size"]
    amount = shares * req.bid_price

    # Generate a unique application ID
    import time
    app_id = f"APP{int(time.time() * 1000) % 1000000:06d}"
    
    # Create application object
    app_obj = {
        "id": app_id,
        "broker": req.broker,
        "ipo_symbol": req.ipo_symbol,
        "ipo_name": ipo["company_name"],
        "lots": req.lots,
        "shares": shares,
        "bid_price": req.bid_price,
        "amount": round(amount, 2),
        "upi_id": req.upi_id,
        "status": "Applied",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Persist
    apps = load_ipo_applications()
    apps.insert(0, app_obj)
    save_ipo_applications(apps)

    return app_obj

@app.delete("/api/ipos/applications/{app_id}")
async def cancel_ipo_application(app_id: str):
    apps = load_ipo_applications()
    filtered_apps = [a for a in apps if a["id"] != app_id]
    
    if len(apps) == len(filtered_apps):
        raise HTTPException(status_code=404, detail="IPO application not found.")
        
    save_ipo_applications(filtered_apps)
    return {"status": "success", "message": f"IPO bid {app_id} cancelled successfully."}


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()


async def broadcast_updates_loop():
    while True:
        await asyncio.sleep(2)
        if manager.active_connections:
            try:
                portfolios_data = await get_all_portfolios()
                await manager.broadcast({
                    "type": "update",
                    "portfolios": portfolios_data
                })
            except Exception as e:
                print(f"Error in broadcast loop: {e}")


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial data immediately
        portfolios_data = await get_all_portfolios()
        history_data = await get_history()
        await websocket.send_json({
            "type": "initial",
            "portfolios": portfolios_data,
            "history": history_data
        })
        while True:
            # Keep connection open and respond to client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket endpoint error: {e}")
        manager.disconnect(websocket)

# Mount static files at root
# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
