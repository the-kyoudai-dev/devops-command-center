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
    created_at_utc = sa.Column(sa.DateTime, default=datetime.utcnow)
    modified_at_utc = sa.Column(sa.DateTime, default=datetime.utcnow)
    status = sa.Column(sa.String(20), default="active", index=True)
    content_preview = sa.Column(sa.Text)

class SystemEvent(Base):
    __tablename__ = "system_events"
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    event_type = sa.Column(sa.String(50), nullable=False, index=True)
    file_path = sa.Column(sa.Text, nullable=False)
    timestamp_utc = sa.Column(sa.DateTime, default=datetime.utcnow, index=True)
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
        elif event_type in ("created", "modified", "moved"):
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
                "created_at_utc": datetime.utcfromtimestamp(stat.st_ctime),
                "modified_at_utc": datetime.utcfromtimestamp(stat.st_mtime),
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
        current_port = config.port
        for _ in range(5): # Try up to 5 ports
            try:
                logging.info(f"Attempting to start server on {config.host}:{current_port}")
                uvicorn.run(app, host=config.host, port=current_port)
                break # Exit loop if uvicorn starts and then exits gracefully
            except OSError as e:
                if e.errno in (98, 10048): # Handle "Address already in use"
                    logging.warning(f"Port {current_port} is in use. Trying port {current_port + 1}.")
                    current_port += 1
                else:
                    logging.critical(f"An unexpected OS error occurred: {e}")
                    raise
        else:
            logging.critical("Could not start server after several attempts. All tried ports were in use.")
    finally:
        db_manager.stop_monitoring()
        logging.info("System shutdown complete.")

def run_server(config: KKSDBConfig):
    db_manager = KKSManager(config)
    db_manager.start_monitoring()
    
    app = create_kks_app(db_manager)
    
    try:
        current_port = config.port
        for _ in range(5): # Try up to 5 ports
            try:
                logging.info(f"Attempting to start server on {config.host}:{current_port}")
                uvicorn.run(app, host=config.host, port=current_port)
                break # Exit loop if uvicorn starts and then exits gracefully
            except (OSError, RuntimeError) as e:
                if "Address already in use" in str(e) or e.errno in (98, 10048):
                    logging.warning(f"Port {current_port} is in use. Trying port {current_port + 1}.")
                    current_port += 1
                else:
                    logging.critical(f"An unexpected OS error occurred: {e}")
                    raise
        else:
            logging.critical("Could not start server after several attempts. All tried ports were in use.")
    finally:
        db_manager.stop_monitoring()
        logging.info("System shutdown complete.")

if __name__ == "__main__":
    config = KKSDBConfig()
    logging.basicConfig(level=config.log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run_server(config)