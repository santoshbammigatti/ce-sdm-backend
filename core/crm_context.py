import json
from pathlib import Path
from typing import Dict, Any, Optional

_DATA_DIR = Path("data")
_orders = None
_customers = None

def _load_json(name: str):
    with (_DATA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)

def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    global _orders
    if _orders is None:
        _orders = {o["order_id"]: o for o in _load_json("orders.json")}
    return _orders.get(order_id)

def get_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    global _customers
    if _customers is None:
        _customers = {c["customer_id"]: c for c in _load_json("customers.json")}
    return _customers.get(customer_id)