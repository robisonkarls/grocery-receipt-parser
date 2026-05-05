-- Grocery Receipt Database Schema
-- For analytics, trends, and purchase predictions

CREATE TABLE IF NOT EXISTS receipts (
  id TEXT PRIMARY KEY,
  store_name TEXT NOT NULL,
  store_location TEXT,
  receipt_date DATE NOT NULL,
  receipt_time TIME,
  total_amount REAL NOT NULL,
  tax_amount REAL,
  subtotal REAL,
  payment_method TEXT,
  transaction_id TEXT,
  markdown_path TEXT NOT NULL,
  image_path TEXT,
  ocr_method TEXT,
  ocr_confidence REAL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  name TEXT NOT NULL,
  quantity REAL DEFAULT 1,
  unit_price REAL,
  total_price REAL NOT NULL,
  category TEXT,
  line_number INTEGER,
  FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS purchase_patterns (
  item_name TEXT PRIMARY KEY,
  normalized_name TEXT,
  avg_days_between_purchase REAL,
  last_purchase_date DATE,
  purchase_count INTEGER DEFAULT 1,
  avg_price REAL,
  min_price REAL,
  max_price REAL,
  preferred_store TEXT,
  preferred_category TEXT
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_store ON receipts(store_name);
CREATE INDEX IF NOT EXISTS idx_receipts_created ON receipts(created_at);
CREATE INDEX IF NOT EXISTS idx_items_receipt ON items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_patterns_last_purchase ON purchase_patterns(last_purchase_date);
