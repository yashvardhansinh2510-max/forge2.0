#!/usr/bin/env python3
"""
Debug rate limit - check what IP the backend sees
"""

import requests

BASE_URL = "https://forge-polish-sprint.preview.emergentagent.com/api"

# Make a request and check headers
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": "test@example.com", "password": "wrong"}
)

print("Response status:", response.status_code)
print("Response:", response.json())

# Try to see what IP the backend might be seeing
import socket
hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)
print(f"\nLocal hostname: {hostname}")
print(f"Local IP: {local_ip}")
