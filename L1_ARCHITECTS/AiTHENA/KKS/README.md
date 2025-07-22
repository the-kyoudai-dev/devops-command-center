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