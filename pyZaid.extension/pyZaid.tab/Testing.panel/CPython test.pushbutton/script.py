#! python3
# -*- coding: utf-8 -*-

import sys
# Replace this path with the EXACT path to your Python 3.12.10 site-packages
# sys.path.append(r"C:\Users\shaik\AppData\Local\Programs\Python\Python312\Lib\site-packages")

# 1. Print current execution pathways for debugging
print("Active Python Version: " + sys.version)

try:
    # 2. Test standard library and external pip installations
    import numpy as np
    import openpyxl
    import clr  # provided by pythonnet
    
    print("SUCCESS: NumPy version " + str(np.__version__) + " loaded.")
    print("SUCCESS: Openpyxl version " + str(openpyxl.__version__) + " loaded.")
    print("SUCCESS: PythonNet CLR loaded.")
    
except Exception as e:
    print("ERROR loading external libraries: " + str(e))
