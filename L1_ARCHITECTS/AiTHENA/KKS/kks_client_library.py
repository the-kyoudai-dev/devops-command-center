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