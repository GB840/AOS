import os
import subprocess
import sys

os.environ["DEER_FLOW_AUTH_DISABLED"] = "1"

os.chdir(r"d:\AOS\external\deer-flow\backend")

subprocess.run([sys.executable, "-m", "uvicorn", "app.gateway.app:app", "--host", "0.0.0.0", "--port", "8080"])
