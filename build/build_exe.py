import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_standalone_exe():
    """
    Automated PyInstaller Builder for KURO 2.0.
    Bundles KURO CLI, prompt templates, tools, and assets into dist/KURO.exe.
    """
    print("=" * 60)
    print(" KURO 2.0  Automated PyInstaller Executable Builder")
    print("=" * 60)

    # Check if pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("[Notice] Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    base_dir = Path(__file__).resolve().parent.parent
    main_script = base_dir / "main.py"
    ico_file = base_dir / "assets" / "kuro_icon.ico"
    png_file = base_dir / "assets" / "kuro_icon.png"
    icon_path = ico_file if ico_file.exists() else png_file

    # PyInstaller flags
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=KURO",
        "--onefile",
        "--console",
        f"--icon={icon_path}",
        f"--add-data={base_dir / 'core'};core",
        f"--add-data={base_dir / 'tools'};tools",
        f"--add-data={base_dir / 'brain'};brain",
        f"--add-data={base_dir / 'assets'};assets",
        "--clean",
        str(main_script)
    ]

    print(f"[Build] Running command:\n{' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(base_dir))

    if res.returncode == 0:
        exe_path = base_dir / "dist" / "KURO.exe"
        print("\n" + "=" * 60)
        print(" BUILD SUCCESSFUL!")
        print(f" Standalone Executable Location: {exe_path}")
        print("=" * 60 + "\n")
    else:
        print("\n[FAIL] PyInstaller build failed. Check logs above.")

if __name__ == "__main__":
    build_standalone_exe()
