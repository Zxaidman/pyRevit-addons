import os
import subprocess
import sys

# 1. DEFINE YOUR MANUALLY CONTROLLED DEPENDENCIES HERE
# Simply list package names as space-separated strings.
# You can also add specific versions if needed (e.g., "openpyxl==3.1.5")
PY3_DEPENDENCIES = "numpy openpyxl pythonnet"
PY2_DEPENDENCIES = "openpyxl"

# 2. Setup folder pathways relative to this script
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.normpath(os.path.join(TOOLS_DIR, "..", "pyZaid.extension", "lib"))

def deploy_libraries(dependencies_string, subfolder):
    # Split the string into a clean Python list of packages
    packages = [pkg.strip() for pkg in dependencies_string.split() if pkg.strip()]
    
    if not packages:
        print(f"[INFO] No packages specified for lib/{subfolder}. Skipping.")
        return

    target_path = os.path.join(LIB_DIR, subfolder)
    os.makedirs(target_path, exist_ok=True)
    
    print(f"\n[PROCESS] Deploying to lib/{subfolder}...")
    print(f"          Packages: {packages}")
    
    # Run the standard pip installation using your current Python environment
    cmd = [
        sys.executable, "-m", "pip", 
        "install", 
        "--target", target_path, 
        "--upgrade"
    ] + packages
    
    subprocess.check_call(cmd)

def clean_metadata_clutter():
    print("\n[PROCESS] Sweeping away redundant .dist-info tracking metadata folders...")
    for sub in ['py2', 'py3']:
        sub_path = os.path.join(LIB_DIR, sub)
        if os.path.exists(sub_path):
            for item in os.listdir(sub_path):
                item_path = os.path.join(sub_path, item)
                # Remove messy metadata folders that pip generates
                if os.path.isdir(item_path) and (item.endswith('.dist-info') or item.endswith('.egg-info')):
                    print(f"          Removing: lib/{sub}/{item}")
                    subprocess.call(f'rmdir /s /q "{item_path}"', shell=True)

if __name__ == "__main__":
    print("====================================================")
    print(" MANUALLY CONTROLLED PYZAID DEPENDENCY PROVISIONER  ")
    print("====================================================")
    
    try:
        # Deploy CPython 3 libraries
        deploy_libraries(PY3_DEPENDENCIES, "py3")
        
        # Deploy IronPython 2 libraries
        deploy_libraries(PY2_DEPENDENCIES, "py2")
        
        # Keep things clean
        clean_metadata_clutter()
        
        print("\n====================================================")
        print(" SUCCESS: All requested libraries deployed cleanly! ")
        print("====================================================\n")
        
    except Exception as e:
        print(f"\n[CRITICAL ERROR]: {str(e)}")
