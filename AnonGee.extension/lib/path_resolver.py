# -*- coding: utf-8 -*-
import sys
import os

def update_paths():
    """Dynamically resolves and injects the correct site-packages folder."""
    # Find the path of this current file (inside /lib)
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check Python version and point to the target package directory
    if sys.version_info.major == 3:
        target_package_dir = os.path.join(lib_dir, "py3")
    else:
        target_package_dir = os.path.join(lib_dir, "py2")
        
    # Inject it to the front of the path array if found
    if os.path.exists(target_package_dir) and target_package_dir not in sys.path:
        sys.path.insert(0, target_package_dir)