import os
import subprocess
import sys

if __name__ == "__main__":
    # Render sets the PORT environment variable for Web Services
    port = os.environ.get("PORT", "8501")
    
    # Run the Streamlit app
    # This allows Render to start the Streamlit server using `python main.py`
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        port,
        "--server.address",
        "0.0.0.0"
    ]
    
    subprocess.run(cmd)
