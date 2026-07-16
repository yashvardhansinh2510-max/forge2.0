#!/usr/bin/env python3
"""
Simple rate limit test - just hammer with wrong password
"""

import requests
import time

BASE_URL = "https://ux-audit-2.preview.emergentagent.com/api"
OWNER_EMAIL = "owner@forge.app"

print("Simple rate limit test - 15 consecutive failed attempts")
print("="*80)

for i in range(15):
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": OWNER_EMAIL, "password": "WrongPassword123"}
    )
    
    print(f"Attempt {i+1}: {response.status_code}")
    
    if response.status_code == 429:
        print(f"\n✅ Rate limit triggered at attempt {i+1}")
        print(f"Message: {response.json().get('detail', '')}")
        break
    
    time.sleep(0.2)
else:
    print(f"\n❌ Rate limit NOT triggered after 15 attempts")
