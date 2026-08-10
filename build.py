import subprocess
import sys
import os
import shutil


def clean_build_dirs():
    """Remove build and dist folders if they exist to ensure a clean build."""
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Removing existing '{folder}' directory...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Warning: Could not remove '{folder}' folder: {e}")


def run_build():
    """Run the PyInstaller build process."""
    print("Starting Scribe Dictation build process...")
    clean_build_dirs()

    spec_path = "scribe-dictation.spec"
    if not os.path.exists(spec_path):
        print(f"Error: Specification file '{spec_path}' not found!")
        sys.exit(1)

    # Use uv run to ensure we run inside the correct virtual environment
    command = ["uv", "run", "pyinstaller", "--clean", spec_path]
    print(f"Executing: {' '.join(command)}")

    try:
        result = subprocess.run(command, check=True)
        if result.returncode == 0:
            print("\n" + "=" * 50)
            print("BUILD SUCCESSFUL!")
            print(
                f"Executable is located at: {os.path.abspath('dist/ScribeDictation.exe')}"
            )
            print("=" * 50)
        else:
            print(f"Build failed with exit code: {result.returncode}")
            sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred during building: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_build()
