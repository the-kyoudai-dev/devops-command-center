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
        
        config = KKSDBConfig()
        # Use an in-memory DB for testing to avoid side-effects
        config.sqlite_path = ':memory:'
        manager = KKSManager(config)
        print("   [OK] KKSManager initialized successfully.")

        client = KKSClient()
        print("   [OK] KKSClient initialized successfully.")
        
        print("[OK] All system tests passed.")
        return True
    except Exception as e:
        print(f"[FAIL] A system test failed: {e}")
        return False

def start_server():
    """Starts the KKS main database server as a background process."""
    print("[INFO] Attempting to start KKS server...")
    server_script = os.path.join(os.path.dirname(__file__), 'kks_live_db_main.py')
    try:
        # Use Popen for non-blocking execution
        process = subprocess.Popen([sys.executable, server_script], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        print(f"[OK] KKS server process started with PID: {process.pid}.")
        print("[INFO] Allowing 5 seconds for server to initialize...")
        time.sleep(5)
        
        # Verify server is running
        for i in range(5):
            port = 8000 + i
            try:
                response = httpx.get(f"http://127.0.0.1:{port}", timeout=1.0)
                if response.status_code == 200:
                    print(f"[OK] Server is responsive on port {port}.")
                    return
            except httpx.RequestError:
                continue
        print("[FAIL] Could not connect to the server after starting. Please check the server logs for errors.")

    except FileNotFoundError:
        print(f"[CRITICAL] Could not find the server script: {server_script}")
    except Exception as e:
        print(f"[CRITICAL] An unexpected error occurred while starting the server: {e}")

def main():
    parser = argparse.ArgumentParser(description="KKS Constitutional Startup Script")
    parser.add_argument("command", choices=["install", "test", "start", "full_init"], help="The command to execute.")
    args = parser.parse_args()

    if args.command == "install":
        check_dependencies()
    elif args.command == "test":
        if not check_dependencies(): sys.exit(1)
        run_tests()
    elif args.command == "start":
        if not check_dependencies(): sys.exit(1)
        start_server()
    elif args.command == "full_init":
        print("--- KKS Full Constitutional Initialization ---")
        if not check_dependencies(): sys.exit(1)
        if not run_tests(): sys.exit(1)
        start_server()
        print("--- Initialization Complete ---")

if __name__ == "__main__":
    main()