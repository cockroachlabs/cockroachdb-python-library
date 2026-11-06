"""Make the flat example modules importable when running pytest from here."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
