from fastapi.testclient import TestClient
from backend.main import app, registry


client = TestClient(app)

def test_get_brokers():
    response = client.get("/api/brokers")
    assert response.status_code == 200
    data = response.json()
    assert "supported" in data
    assert "active" in data
    assert "Zerodha" in data["supported"]
    assert "Alpaca" in data["supported"]
    assert "Groww" in data["supported"]
    assert "Motilal Oswal" in data["supported"]

def test_register_and_unregister_broker():
    # Clean registry first
    try:
        client.delete("/api/brokers/Alpaca")
    except:
        pass
        
    # Register Alpaca
    payload = {
        "broker": "Alpaca",
        "credentials": {
            "api_key": "test_key",
            "secret_key": "test_secret"
        }
    }
    response = client.post("/api/brokers", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Check that it is active
    response = client.get("/api/brokers")
    assert "Alpaca" in response.json()["active"]
    
    # Get Portfolios
    response = client.get("/api/portfolios")
    assert response.status_code == 200
    portfolios_data = response.json()
    assert portfolios_data["summary"]["active_count"] >= 1
    
    # Get Positions
    response = client.get("/api/positions")
    assert response.status_code == 200
    
    # Get Quote
    response = client.get("/api/quote/Alpaca/AAPL")
    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
    
    # Place buy order
    order_payload = {
        "broker": "Alpaca",
        "symbol": "AAPL",
        "qty": 2,
        "side": "BUY"
    }
    response = client.post("/api/orders", json=order_payload)
    assert response.status_code == 200
    order_data = response.json()
    assert order_data["status"] == "placed"
    assert order_data["qty"] == 2
    
    # Place sell order
    order_payload = {
        "broker": "Alpaca",
        "symbol": "AAPL",
        "qty": 1,
        "side": "SELL"
    }
    response = client.post("/api/orders", json=order_payload)
    assert response.status_code == 200
    
    # Unregister Alpaca
    response = client.delete("/api/brokers/Alpaca")
    assert response.status_code == 200
    
    # Verify not active
    response = client.get("/api/brokers")
    assert "Alpaca" not in response.json()["active"]

def test_ipo_endpoints():
    # 1. Get IPOs
    response = client.get("/api/ipos")
    assert response.status_code == 200
    ipos_data = response.json()
    assert len(ipos_data) >= 3
    assert any(i["symbol"] == "SWIGGY" for i in ipos_data)
    
    # 2. Get applications
    response = client.get("/api/ipos/applications")
    assert response.status_code == 200
    
    # Register mock broker to test apply endpoint
    register_payload = {
        "broker": "Zerodha",
        "credentials": {
            "api_key": "test_key",
            "access_token": "test_token"
        }
    }
    client.post("/api/brokers", json=register_payload)
    
    # Apply for IPO
    apply_payload = {
        "broker": "Zerodha",
        "ipo_symbol": "SWIGGY",
        "lots": 2,
        "bid_price": 385.0,
        "upi_id": "test@upi"
    }
    response = client.post("/api/ipos/apply", json=apply_payload)
    assert response.status_code == 200
    app_data = response.json()
    assert app_data["status"] == "Applied"
    assert app_data["shares"] == 76
    
    # Verify application list
    response = client.get("/api/ipos/applications")
    assert response.status_code == 200
    apps = response.json()
    assert any(a["id"] == app_data["id"] for a in apps)
    
    # Cancel bid
    response = client.delete(f"/api/ipos/applications/{app_data['id']}")
    assert response.status_code == 200
    
    # Clean up broker
    client.delete("/api/brokers/Zerodha")

if __name__ == "__main__":
    try:
        print("Running test_get_brokers...")
        test_get_brokers()
        print("Running test_register_and_unregister_broker...")
        test_register_and_unregister_broker()
        print("Running test_ipo_endpoints...")
        test_ipo_endpoints()
        print("\nAll backend integration tests passed successfully!")
    except AssertionError as e:
        print(f"\nTest failed with assertion error: {e}")
        import sys
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import sys
        sys.exit(1)
