import sys
import os

# Get the absolute path of the directory containing this file (tiffin-cpac)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add this directory to the Python system path so it can find app.py
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import your Flask app
# This assumes your Flask instance is named 'app' inside your 'app.py' file
from app import app as application