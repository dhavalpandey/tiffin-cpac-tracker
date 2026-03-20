import os
import sys

# Tell the server to look in this directory for your app
sys.path.insert(0, os.path.dirname(__file__))

# Import your Flask app (from app.py) and rename it to 'application'
# Passenger explicitly requires the app variable to be named 'application'
from app import app as application