# Pytest configuration & path setup
# Ensures the repository root (with 'backend' package) is importable when running pytest from subdirectories.

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
