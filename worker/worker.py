import time
import os
from dotenv import load_dotenv

load_dotenv()

print("Worker service started. Waiting for jobs...")
while True:
    time.sleep(10)
