import os
import subprocess
import sys

def build():
    main_script = "main.py"
    output_dir = "build"
    
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--enable-plugin=tk-inter",
        f"--output-dir={output_dir}",
        "--remove-output",
        main_script
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)

if __name__ == "__main__":
    build()
