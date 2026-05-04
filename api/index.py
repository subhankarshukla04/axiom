import sys
import os

# Make the repo root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel looks for a callable named 'app' or 'handler'
handler = app
