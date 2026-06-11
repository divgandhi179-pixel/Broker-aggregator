import os
import json
import asyncio
import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.broker_registry import BrokerRegistry
from backend.database import get_db, init_db, SessionLocal, User, Broker, Order, IPOApplication
from backend.auth import (
    get_current_user,
    get_ws_user_helper,
    verify_password,
    get_password_hash,
    create_access_token,
    validate_email_address,
)

app = FastAPI(title="Apex Broker Aggregator API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registry instance for active adapter connections
registry = BrokerRegistry()

# Pydantic Schemas
class UserRegister(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

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


# Initialize and load active sessions on startup
def load_all_active_brokers():
    db = SessionLocal()
    try:
        db_brokers = db.query(Broker).all()
        for b in db_brokers:
            try:
                registry.register(b.user_id, b.broker_name, **b.credentials)
            except Exception as e:
                print(f"Failed to register broker {b.broker_name} for user {b.user_id} on startup: {e}")
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    # Create tables
    init_db()
    # Load broker sessions
    load_all_active_brokers()
    # Start Websocket update loop
    asyncio.create_task(broadcast_updates_loop())


# --- AUTHENTICATION ENDPOINTS ---

@app.post("/api/auth/register")
async def register_user(req: UserRegister, db: Session = Depends(get_db)):
    # 1. Validate email syntax
    try:
        email_normalized = validate_email_address(req.email)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email format: {str(e)}"
        )
    
    # 2. Check if username or email already exists
    existing_user = db.query(User).filter(User.email == email_normalized).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )
    
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )

    # 3. Create user
    hashed_pwd = get_password_hash(req.password)
    new_user = User(
        email=email_normalized,
        username=req.username,
        password_hash=hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate token
    token = create_access_token(data={"sub": new_user.email})
    return {
        "status": "success",
        "message": "User registered successfully.",
        "access_token": token,
        "token_type": "bearer",
        "user": {"email": new_user.email, "username": new_user.username}
    }


@app.post("/api/auth/login")
async def login_user(req: UserLogin, db: Session = Depends(get_db)):
    # 1. Find user
    user = db.query(User).filter(User.email == req.email.strip()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
        
    token = create_access_token(data={"sub": user.email})
    return {
        "status": "success",
        "message": "Logged in successfully.",
        "access_token": token,
        "token_type": "bearer",
        "user": {"email": user.email, "username": user.username}
    }


# --- SECURED BROKER MANAGEMENT ENDPOINTS ---

@app.get("/api/brokers")
async def get_brokers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    supported = ["Zerodha", "Alpaca", "Groww", "Motilal Oswal"]
    # Get active brokers registered in database for this user
    user_brokers = db.query(Broker).filter(Broker.user_id == current_user.id).all()
    active = [b.broker_name for b in user_brokers]
    return {
        "supported": supported,
        "active": active
    }


@app.post("/api/brokers")
async def register_broker(
    config: BrokerConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if config.broker not in ["Zerodha", "Alpaca", "Groww", "Motilal Oswal"]:
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {config.broker}")
    
    # Check if already registered in DB
    existing = db.query(Broker).filter(
        Broker.user_id == current_user.id,
        Broker.broker_name == config.broker
    ).first()
    
    try:
        # Register in registry cache
        registry.register(current_user.id, config.broker, **config.credentials)
        
        # Save to DB
        if existing:
            existing.credentials = config.credentials
        else:
            new_broker = Broker(
                user_id=current_user.id,
                broker_name=config.broker
            )
            new_broker.credentials = config.credentials
            db.add(new_broker)
        
        db.commit()
        return {"status": "success", "message": f"{config.broker} broker registered successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/brokers/{name}")
async def unregister_broker(
    name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    existing = db.query(Broker).filter(
        Broker.user_id == current_user.id,
        Broker.broker_name == name
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail=f"Broker {name} is not connected.")
        
    try:
        # Unregister from registry
        registry.unregister(current_user.id, name)
        # Delete from DB
        db.delete(existing)
        db.commit()
        return {"status": "success", "message": f"{name} broker disconnected."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# Helper function to get portfolios for a specific user
async def get_all_portfolios_for_user(user: User, db: Session) -> dict:
    active_brokers = registry.all_for_user(user.id)
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


@app.get("/api/portfolios")
async def get_all_portfolios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await get_all_portfolios_for_user(current_user, db)


@app.get("/api/positions")
async def get_all_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    active_brokers = registry.all_for_user(current_user.id)
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
async def get_broker_quote(
    broker_name: str,
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    try:
        broker = registry.get(current_user.id, broker_name)
        quote = await broker.get_quote(symbol)
        return quote
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/orders")
async def place_order(
    order: OrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        broker = registry.get(current_user.id, order.broker)
        # Execute order on the adapter
        res = await broker.place_order(
            symbol=order.symbol,
            qty=order.qty,
            side=order.side,
            order_type=order.order_type
        )
        
        # Get quote for exact execution price
        quote = await broker.get_quote(order.symbol)
        exec_price = quote["ltp"]
        
        # Save to database
        db_order = Order(
            user_id=current_user.id,
            broker_name=order.broker,
            order_id=res["order_id"],
            symbol=order.symbol.upper(),
            qty=order.qty,
            side=order.side.upper(),
            execution_price=exec_price,
            status="placed",
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.add(db_order)
        db.commit()
        
        order_log = res.copy()
        order_log["timestamp"] = db_order.timestamp
        order_log["execution_price"] = exec_price
        
        return order_log
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/history")
async def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.id.desc()).all()
    return [
        {
            "broker": o.broker_name,
            "order_id": o.order_id,
            "symbol": o.symbol,
            "qty": o.qty,
            "side": o.side,
            "execution_price": o.execution_price,
            "status": o.status,
            "timestamp": o.timestamp
        }
        for o in orders
    ]


# --- IPO PORTAL ENDPOINTS ---

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

@app.get("/api/ipos")
async def get_ipos():
    return MOCK_IPOS


@app.get("/api/ipos/applications")
async def get_ipo_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    apps = db.query(IPOApplication).filter(IPOApplication.user_id == current_user.id).order_by(IPOApplication.id.desc()).all()
    return [
        {
            "id": f"APP{a.id:06d}",
            "broker": a.broker_name,
            "ipo_symbol": a.ipo_symbol,
            "ipo_name": a.ipo_name,
            "lots": a.lots,
            "shares": a.shares,
            "bid_price": a.bid_price,
            "amount": a.amount,
            "upi_id": a.upi_id,
            "status": a.status,
            "timestamp": a.timestamp
        }
        for a in apps
    ]


@app.post("/api/ipos/apply")
async def apply_ipo(
    req: IPOApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        broker = registry.get(current_user.id, req.broker)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Broker {req.broker} is not connected. Connect the broker first.")

    ipo = next((i for i in MOCK_IPOS if i["symbol"] == req.ipo_symbol), None)
    if not ipo:
        raise HTTPException(status_code=400, detail=f"IPO {req.ipo_symbol} not found.")

    if ipo["status"] != "OPEN":
        raise HTTPException(status_code=400, detail=f"IPO {req.ipo_symbol} is not open for bidding.")

    if req.bid_price < ipo["min_price"] or req.bid_price > ipo["max_price"]:
        raise HTTPException(status_code=400, detail=f"Bid price must be between {ipo['price_range']}.")

    shares = req.lots * ipo["lot_size"]
    amount = shares * req.bid_price

    try:
        app_obj = IPOApplication(
            user_id=current_user.id,
            broker_name=req.broker,
            ipo_symbol=req.ipo_symbol,
            ipo_name=ipo["company_name"],
            lots=req.lots,
            shares=shares,
            bid_price=req.bid_price,
            amount=round(amount, 2),
            upi_id=req.upi_id,
            status="Applied",
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.add(app_obj)
        db.commit()
        db.refresh(app_obj)

        return {
            "id": f"APP{app_obj.id:06d}",
            "broker": app_obj.broker_name,
            "ipo_symbol": app_obj.ipo_symbol,
            "ipo_name": app_obj.ipo_name,
            "lots": app_obj.lots,
            "shares": app_obj.shares,
            "bid_price": app_obj.bid_price,
            "amount": app_obj.amount,
            "upi_id": app_obj.upi_id,
            "status": app_obj.status,
            "timestamp": app_obj.timestamp
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/ipos/applications/{app_id}")
async def cancel_ipo_application(
    app_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Extract ID integer from code (e.g. APP000123 -> 123)
        db_id = int(app_id.replace("APP", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid application ID format.")
        
    app_obj = db.query(IPOApplication).filter(
        IPOApplication.id == db_id,
        IPOApplication.user_id == current_user.id
    ).first()
    
    if not app_obj:
        raise HTTPException(status_code=404, detail="IPO application not found.")
        
    try:
        db.delete(app_obj)
        db.commit()
        return {"status": "success", "message": f"IPO bid {app_id} cancelled successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# --- WEBSOCKET CLIENT SYNC ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {} # user_id -> List[WebSocket]

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast_to_user(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            for connection in list(self.active_connections[user_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(user_id, connection)

manager = ConnectionManager()


async def broadcast_updates_loop():
    while True:
        await asyncio.sleep(2)
        if manager.active_connections:
            db = SessionLocal()
            try:
                for user_id in list(manager.active_connections.keys()):
                    try:
                        user = db.query(User).filter(User.id == user_id).first()
                        if user:
                            portfolios_data = await get_all_portfolios_for_user(user, db)
                            await manager.broadcast_to_user(user_id, {
                                "type": "update",
                                "portfolios": portfolios_data
                            })
                    except Exception as e:
                        print(f"Error in websocket broadcast for user {user_id}: {e}")
            except Exception as e:
                print(f"Error in broadcast loop: {e}")
            finally:
                db.close()


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    db = SessionLocal()
    user = None
    try:
        user = get_ws_user_helper(token, db)
    except Exception as e:
        # Reject connection if token is invalid
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        db.close()
        return

    await manager.connect(user.id, websocket)
    try:
        # Send initial user portfolios & order history
        portfolios_data = await get_all_portfolios_for_user(user, db)
        
        # Format history data
        orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.desc()).all()
        history_data = [
            {
                "broker": o.broker_name,
                "order_id": o.order_id,
                "symbol": o.symbol,
                "qty": o.qty,
                "side": o.side,
                "execution_price": o.execution_price,
                "status": o.status,
                "timestamp": o.timestamp
            }
            for o in orders
        ]
        
        await websocket.send_json({
            "type": "initial",
            "portfolios": portfolios_data,
            "history": history_data
        })
        
        while True:
            # Maintain active connection, respond to client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
    except Exception as e:
        print(f"WebSocket endpoint error for user {user.id if user else 'unknown'}: {e}")
        if user:
            manager.disconnect(user.id, websocket)
    finally:
        db.close()


# Mount static assets at root
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
