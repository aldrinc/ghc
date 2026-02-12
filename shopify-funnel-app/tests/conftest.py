import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("SHOPIFY_APP_API_KEY", "test_key")
os.environ.setdefault("SHOPIFY_APP_API_SECRET", "test_secret")
os.environ.setdefault("SHOPIFY_APP_SCOPES", "read_products,write_products,read_orders")
os.environ.setdefault("SHOPIFY_APP_BASE_URL", "https://example.ngrok.app")
os.environ.setdefault("SHOPIFY_INTERNAL_API_TOKEN", "internal_token")
os.environ.setdefault("SHOPIFY_APP_DB_URL", "sqlite:///./test_shopify_app.db")
os.environ.setdefault("SHOPIFY_ENABLE_ORDER_FORWARDING", "false")
