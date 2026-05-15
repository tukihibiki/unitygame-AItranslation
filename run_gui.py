#!/usr/bin/env python3
"""Launch the Hanhua GUI launcher."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import main

if __name__ == "__main__":
    main()
