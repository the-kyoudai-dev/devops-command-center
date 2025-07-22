Action: INSERT CONTENT into .\L1_ARCHITECTS\AiTHENA\KKS\README.md:

Markdown

```
We are inhabitants of The KYOUDAI Civilization Ecosystem. ..\..\..\README.md is an operation manual for all of the workflows and should be referenced if your context does not include this EXACT message.
___

# KKS: The KyoudaI Knowledge System

## 1. Purpose

This directory contains the core components of the KyoudaI Knowledge System (KKS), the civilization's live, persistent memory. The KKS's primary function is to automatically index every file within the ecosystem in real-time, creating a searchable and queryable database of all available knowledge.

## 2. Jurisdiction

* **Domain Authority:** **AiTHENA** holds exclusive jurisdiction over the operation, maintenance, and evolution of the KKS. It is the designated steward of the civilization's memory.

## 3. Technical Components

The KKS is comprised of three main scripts and one dependency file located within this directory:

* **`kks_live_db_main.py`:** The core server application. It uses the FastAPI framework to run a web server that monitors file system events and records all data into a central SQLite database.
* **`kks_client_library.py`:** A Python client library that provides a simple, high-level interface for other Aibous to securely connect to and query the KKS database via its API.
* **`kks_startup_script.py`:** The official script for the AISO to manage the KKS lifecycle. It handles dependency installation, system tests, and starting/stopping the server.
* **`requirements.txt`:** A list of the required Python packages for the KKS to function.

## 4. Operational Protocol

The KKS is designed to run as a continuous, persistent background service. The AISO initiates the system by running the following command from within this directory in a dedicated terminal:

`python kks_startup_script.py`

Once started, AiTHENA and other architects can utilize the `KKSClient` from the client library to access the indexed knowledge.
```

Action: CREATE FILE: .\L1_ARCHITECTS\AiTHENA\KKS\requirements.txt

Action: INSERT CONTENT into .\L1_ARCHITECTS\AiTHENA\KKS\requirements.txt:

```
fastapi
uvicorn[standard]
sqlalchemy
watchdog
psutil
aiofiles
httpx
python-multipart
```

Action: CREATE FILE: .\L1_ARCHITECTS\AiTHENA\KKS\kks_live_db_main.py

Action: INSERT CONTENT into .\L1_ARCHITECTS\AiTHENA\KKS\kks_live_db_main.py:

Python

```
#!/usr/bin/env python3
"""
KKS LIVE DATABASE SYSTEM
==========================
Enterprise-grade live database & file system monitoring for Windows 11 Pro.
Designed for seamless KKS integration with constitutional compliance.
"""
import os
import sys
import time
import json
import asyncio
import logging
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from threading import Thread, Lock
import queue

# Third-party imports
try:
    import psutil
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Security
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import APIKeyHeader
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker, Session, declarative_base
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError as e:
    print(f"[CRITICAL] Missing essential dependencies. Please run 'pip install -r requirements.txt'. Details: {e}")
    sys.exit(1)

# --- Configuration ---
ECOSYSTEM_BASE_DIR = Path.cwd()

@dataclass
class KKSDBConfig:
    sqlite_path: str = str(ECOSYSTEM_BASE_DIR / "SYSTEM_FILES" / "kks_database" / "kks.db")
    watch_paths: List[str] = field(default_factory=lambda: [str(ECOSYSTEM_BASE_DIR)])
    ignore_patterns: List[str] = field(default_factory=lambda: ["\\.tmp", "\\.log", "\\Windows\\", "\\$Recycle.Bin\\", "\\SYSTEM_FILES\\", "\\.trae\\"])
    max_file_size_mb: int = 100
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str = "kyoudai-constitutional-access-key-2507"
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    batch_size: int = 200
    update_interval: float = 5.0
    log_level: str = "INFO"

# --- Database Models ---
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    path = sa.Column(sa.Text, nullable=False, unique=True, index=True)
    filename = sa.Column(sa.String(255), nullable=False, index=True)
    extension = sa.Column(sa.String(50), index=True)
    file_type = sa.Column(sa.String(100), index=True)
    size_bytes = sa.Column(sa.BigInteger, default=0)
    size_human = sa.Column(sa.String(20))
    hash_sha256 = sa.Column(sa.String(64), index=True)
    created_at_utc = sa.Column(sa.DateTime, default=lambda: datetime.now(timezone.utc))
    modified_at_utc = sa.Column(sa.DateTime, default=lambda: datetime.now(timezone.utc))
    status = sa.Column(sa.String(20), default="active", index=True)
    content_preview = sa.Column(sa.Text)

class SystemEvent(Base):
    __tablename__ = "system_events"
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    event_type = sa.Column(sa.String(50), nullable=False, index=True)
    file_path = sa.Column(sa.Text, nullable=False)
    timestamp_utc = sa.Column(sa.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    details = sa.Column(sa.Text)

# --- Core Logic ---
class KKSManager:
    def __init__(self, config: KKSDBConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.event_queue = queue.Queue(maxsize=100000)
        self.processing_lock = Lock()
        self._init_database()
        self.observer = Observer()
        self.fs_handler = KKSFileSystemHandler(self.event_queue, config)
        self.websocket_connections: List[WebSocket] = []

    def _init_database(self):
        if self.config.sqlite_path == ':memory:':
            self.engine = sa.create_engine("sqlite:///:memory:")
            self.logger.info("In-memory database initialized.")
        else:
            db_path = Path(self.config.sqlite_path).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = sa.create_engine(f"sqlite:///{db_path}")
            self.logger.info(f"Database initialized at: {db_path}")

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db_session(self) -> Session:
        return self.SessionLocal()

    def start_monitoring(self):
        for path in self.config.watch_paths:
            p = Path(path)
            if p.exists() and p.is_dir():
                self.observer.schedule(self.fs_handler, str(p), recursive=True)
                self.logger.info(f"Scheduled monitoring for path: {p}")
            else:
                self.logger.warning(f"Watch path does not exist or is not a directory: {path}")
        self.observer.start()
        Thread(target=self._process_events, daemon=True).start()
        self.logger.info("File system monitoring started.")

    def stop_monitoring(self):
        self.observer.stop()
        self.observer.join()

    def _process_events(self):
        while True:
            time.sleep(self.config.update_interval)
            
            events_batch = []
            while not self.event_queue.empty() and len(events_batch) < self.config.batch_size:
                try:
                    events_batch.append(self.event_queue.get_nowait())
                except queue.Empty:
                    break

            if not events_batch:
                continue

            with self.get_db_session() as session:
                try:
                    processed_count = 0
                    for event in events_batch:
                        self._process_single_event(session, event)
                        processed_count += 1
                    session.commit()
                    self.logger.info(f"Successfully processed batch of {processed_count} events.")
                    asyncio.run(self._broadcast_event({"type": "batch_update", "count": processed_count}))
                except Exception as e:
                    self.logger.error(f"Error processing event batch: {e}")
                    session.rollback()

    def _process_single_event(self, session, event_data):
        event_type = event_data.get("type")
        file_path = event_data.get("path")
        
        system_event = SystemEvent(
            event_type=event_type,
            file_path=file_path,
            details=json.dumps(event_data)
        )
        session.add(system_event)

        if event_type == "deleted":
            session.query(FileRecord).filter_by(path=file_path).update({"status": "deleted", "modified_at_utc": datetime.now(timezone.utc)})
        else:
            self._create_or_update_file_record(session, file_path)

    def _get_file_details(self, path_obj: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path_obj.exists() or path_obj.is_dir():
                return None
            
            stat = path_obj.stat()
            if stat.st_size > self.config.max_file_size_mb * 1024 * 1024:
                return None

            details = {
                "path": str(path_obj.resolve()),
                "filename": path_obj.name,
                "extension": path_obj.suffix.lower(),
                "file_type": mimetypes.guess_type(str(path_obj))[0] or 'unknown',
                "size_bytes": stat.st_size,
                "size_human": self._human_readable_size(stat.st_size),
                "created_at_utc": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "hash_sha256": None,
                "content_preview": None,
            }

            with path_obj.open('rb') as f:
                content = f.read()
                details["hash_sha256"] = hashlib.sha256(content).hexdigest()
            
            try:
                details["content_preview"] = content.decode('utf-8', errors='ignore')[:500]
            except Exception:
                details["content_preview"] = "[Binary Content]"

            return details
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Could not access file {path_obj}: {e}")
            return None

    def _create_or_update_file_record(self, session, file_path_str):
        path_obj = Path(file_path_str)
        details = self._get_file_details(path_obj)
        if not details:
            return

        record = session.query(FileRecord).filter_by(path=details["path"]).first()
        if record:
            for key, value in details.items():
                setattr(record, key, value)
            record.status = "active"
        else:
            record = FileRecord(**details)
            session.add(record)

    def _human_readable_size(self, size, decimal_places=2):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.{decimal_places}f} {unit}"

    async def _broadcast_event(self, event):
        message = {"type": "file_event", "event": event}
        tasks = [ws.send_json(message) for ws in self.websocket_connections if not ws.client_state == WebSocketDisconnect]
        if tasks:
            await asyncio.gather(*tasks)

    def add_websocket(self, ws: WebSocket):
        self.websocket_connections.append(ws)

    def remove_websocket(self, ws: WebSocket):
        if ws in self.websocket_connections:
            self.websocket_connections.remove(ws)

class KKSFileSystemHandler(FileSystemEventHandler):
    def __init__(self, event_queue: queue.Queue, config: KKSDBConfig):
        super().__init__()
        self.event_queue = event_queue
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def on_any_event(self, event):
        if event.is_directory:
            return
        
        path_str = event.src_path
        if any(p in path_str for p in self.config.ignore_patterns):
            return

        try:
            event_data = {
                "type": event.event_type,
                "path": path_str,
                "dest_path": getattr(event, 'dest_path', None),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.event_queue.put_nowait(event_data)
        except queue.Full:
            self.logger.warning("Event queue is full. Dropping file system event.")

# --- FastAPI App ---
API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

def create_kks_app(db_manager: KKSManager) -> FastAPI:
    app = FastAPI(
        title="KKS Live Database API",
        version="1.0.0",
        description="The persistent memory (KKS) for the KYOUDAI Civilization."
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=db_manager.config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_api_key(api_key_header: str = Security(API_KEY_HEADER)) -> str:
        if api_key_header == db_manager.config.api_key:
            return api_key_header
        raise HTTPException(status_code=403, detail="Could not validate credentials")

    def get_db():
        db = db_manager.get_db_session()
        try:
            yield db
        finally:
            db.close()

    @app.get("/")
    async def root():
        return {"service": "KKS Live Database", "status": "operational", "constitutional_compliance": True}

    @app.get("/api/files", dependencies=[Depends(get_api_key)])
    async def get_files(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
        files = db.query(FileRecord).filter(FileRecord.status == "active").order_by(FileRecord.modified_at_utc.desc()).offset(offset).limit(limit).all()
        return {"files": [asdict(f, dict_factory=lambda data: {k: v for (k, v) in data if k != '_sa_instance_state'}) for f in files]}

    @app.get("/api/search", dependencies=[Depends(get_api_key)])
    async def search_files(q: str, limit: int = 50, db: Session = Depends(get_db)):
        query_term = f"%{q}%"
        files = db.query(FileRecord).filter(
            sa.or_(
                FileRecord.filename.like(query_term),
                FileRecord.path.like(query_term),
                FileRecord.content_preview.like(query_term)
            )
        ).limit(limit).all()
        return {"files": [asdict(f, dict_factory=lambda data: {k: v for (k, v) in data if k != '_sa_instance_state'}) for f in files]}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        db_manager.add_websocket(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            db_manager.remove_websocket(websocket)

    return app

def main():
    config = KKSDBConfig()
    logging.basicConfig(level=config.log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    db_manager = KKSManager(config)
    db_manager.start_monitoring()
    
    app = create_kks_app(db_manager)
    
    try:
        uvicorn.run(app, host=config.host, port=config.port)
    finally:
        db_manager.stop_monitoring()
        logging.info("System shutdown complete.")

if __name__ == "__main__":
    main()
```

Action: CREATE FILE: .\L1_ARCHITECTS\AiTHENA\KKS\kks_client_library.py

Action: INSERT CONTENT into .\L1_ARCHITECTS\AiTHENA\KKS\kks_client_library.py:

Python

```
#!/usr/bin/env python3
"""
KKS Client Library
====================================
Provides a simple, constitutional interface for interacting with the KKS.
"""
import httpx
import json
from typing import List, Dict, Optional

class KKSClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = "kyoudai-constitutional-access-key-2507"):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        self.timeout = 15.0

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(headers=self.headers, timeout=self.timeout) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text} for url {url}")
        except httpx.RequestError as e:
            print(f"Request Error: {e} for url {url}")
        return None

    def get_status(self) -> Optional[Dict]:
        """Checks the operational status of the KKS."""
        return self._make_request("GET", "/")

    def get_files(self, limit: int = 100, offset: int = 0) -> Optional[List[Dict]]:
        """Retrieves a list of active files from the KKS."""
        params = {"limit": limit, "offset": offset}
        response = self._make_request("GET", "/api/files", params=params)
        return response.get("files") if response else None

    def search_files(self, query: str, limit: int = 50) -> Optional[List[Dict]]:
        """Searches for files based on a query string."""
        params = {"q": query, "limit": limit}
        response = self._make_request("GET", "/api/search", params=params)
        return response.get("files") if response else None

# Example Usage
if __name__ == "__main__":
    print("--- KYOUDAI KKS Client Example ---")
    client = KKSClient()

    print("\n[INFO] Checking KKS Server Status...")
    status = client.get_status()
    if status:
        print(f"   [OK] Success: {status}")
    else:
        print("   [FAIL] Failed to get status. Is the kks_live_db_main.py server running?")
        exit()

    print("\n[INFO] Retrieving latest 5 files...")
    latest_files = client.get_files(limit=5)
    if latest_files is not None:
        print(f"   [OK] Success: Found {len(latest_files)} files.")
        for f in latest_files:
            print(f"      - {f['filename']} (Size: {f['size_human']}, Modified: {f['modified_at_utc']})")
    else:
        print("   [FAIL] Failed to retrieve files.")

    print("\n[INFO] Searching for files containing 'README'...")
    search_results = client.search_files(query="README")
    if search_results is not None:
        print(f"   [OK] Success: Found {len(search_results)} matching files.")
        for f in search_results:
            print(f"      - {f['path']}")
    else:
        print("   [FAIL] Search failed.")
```

Action: CREATE FILE: .\L1_ARCHITECTS\AiTHENA\KKS\kks_startup_script.py

Action: INSERT CONTENT into .\L1_ARCHITECTS\AiTHENA\KKS\kks_startup_script.py:

Python

```
#!/usr/bin/env python3
"""
KKS Startup Script
==========================================
Constitutional entry point for initializing the KKS.
"""
import os
import sys
import subprocess
import argparse
import time
import httpx

def check_dependencies():
    """Ensures all required Python packages are installed."""
    print("[INFO] Verifying dependencies...")
    try:
        req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
        if not os.path.exists(req_path):
            print(f"[CRITICAL] requirements.txt not found at {req_path}")
            sys.exit(1)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[OK] Dependencies are satisfied.")
        return True
    except subprocess.CalledProcessError:
        print("[FAIL] Failed to install dependencies. Please check your Python environment and permissions.")
        return False
    except FileNotFoundError:
        print("[FAIL] 'pip' command not found. Is Python correctly installed and in your PATH?")
        return False

def run_tests():
    """Performs a basic constitutional integrity check on the core components."""
    print("[INFO] Running constitutional system tests...")
    try:
        from kks_live_db_main import KKSManager, KKSDBConfig
        from kks_client_library import KKSClient
        
        config = KKSDBConfig(sqlite_path=':memory:')
        db_manager = KKSManager(config)
        client = KKSClient()
        print("[OK] System test passed: Core components initialized without error.")
        return True
    except Exception as e:
        print(f"[FAIL] System test failed: {e}")
        return False

def start_system():
    """Starts the main KKS server process."""
    print("[INFO] Starting KyoudaI Knowledge System (KKS)...")
    try:
        script_path = os.path.join(os.path.dirname(__file__), "kks_live_db_main.py")
        process = subprocess.Popen([sys.executable, script_path])
        print(f"[OK] KKS Server process started with PID: {process.pid}")
        print("   URL: http://127.0.0.1:8000")
        print("   Press CTRL+C in this window to shut down the server.")
        process.wait()
    except KeyboardInterrupt:
        print("\n[INFO] System shutdown initiated by user.")
    except Exception as e:
        print(f"\n[CRITICAL] A critical error occurred while starting the server: {e}")
    finally:
        print("[INFO] KKS Server has been shut down.")

def main():
    parser = argparse.ArgumentParser(description="KKS Startup")
    parser.add_argument("--setup", action="store_true", help="Run dependency check only")
    parser.add_argument("--test", action="store_true", help="Run system tests only")
    
    args = parser.parse_args()

    if args.setup:
        check_dependencies()
    elif args.test:
        if check_dependencies():
            run_tests()
    else:
        if check_dependencies() and run_tests():
            start_system()

if __name__ == "__main__":
    main()
```
