#! python3
# -*- coding: utf-8 -*-

# 1. Initialize your dynamic path resolver
import path_resolver
path_resolver.update_paths()

import sys
import os

print("============================================================")
print("PORTABILITY & DEPENDENCY VERIFICATION REPORT")
print("============================================================\n")

# List of modules to verify
modules_to_test = ["numpy", "openpyxl", "pythonnet", "clr"]

for mod_name in modules_to_test:
    try:
        # Dynamically import the module
        module = __import__(mod_name)
        
        # Determine the source file location
        if hasattr(module, "__file__") and module.__file__ is not None:
            mod_path = module.__file__
        else:
            # Built-in or compiled C-extensions embedded in the host might not have a __file__
            mod_path = "Built-in / Embedded Runtime Assembly"
            
        print("✅ [{}] Loaded Successfully".format(mod_name.upper()))
        print("   ↳ Source Path: {}\n".format(mod_path))
        
    except ImportError as e:
        print("❌ [{}] FAILED TO IMPORT".format(mod_name.upper()))
        print("   ↳ Error: {}\n".format(str(e)))

print("============================================================")
print("VERIFICATION COMPLETE")
print("============================================================")