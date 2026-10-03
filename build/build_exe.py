import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_standalone_exe():
    """
    Automated PyInstaller Builder for KURO 2.0 (Production --onedir strategy).
    Bundles KURO CLI, core modules, tools, integrations, and assets into dist/KURO/ folder.
    """
    print("=" * 60)
    print(" KURO 2.0  Automated PyInstaller Directory Executable Builder")
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

    # PyInstaller flags (--onedir strategy for modular production distribution)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=KURO",
        "--onedir",
        "--console",
        f"--icon={icon_path}",
        f"--add-data={base_dir / 'core'};core",
        f"--add-data={base_dir / 'tools'};tools",
        f"--add-data={base_dir / 'integrations'};integrations",
        f"--add-data={base_dir / 'assets'};assets",
        "--hidden-import=ctypes",
        "--hidden-import=edge_tts",
        "--hidden-import=pygame",
        "--hidden-import=speech_recognition",
        "--clean",
        str(main_script)
    ]

    print(f"[Build] Running command:\n{' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(base_dir))

    if res.returncode == 0:
        dist_dir = base_dir / "dist" / "KURO"
        exe_path = dist_dir / "KURO.exe"
        print("\n" + "=" * 60)
        print(" BUILD SUCCESSFUL!")
        print(f" Directory Application Location: {dist_dir}")
        print(f" Executable: {exe_path}")
        print("=" * 60 + "\n")
    else:
        print("\n[FAIL] PyInstaller build failed. Check logs above.")

if __name__ == "__main__":
    build_standalone_exe()
