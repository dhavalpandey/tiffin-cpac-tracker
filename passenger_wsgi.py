import os
import sys

# Add your project directory to the sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import your Flask app (from app.py) and rename it to 'application'
# Phusion Passenger explicitly looks for a variable named 'application'
from app import app as application