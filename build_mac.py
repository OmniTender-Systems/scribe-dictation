"""Cross-platform build script for macOS packaging (.app bundle & DMG image).

Builds PrivacyScribe.app with PyInstaller and packages it into a distributable DMG
using create-dmg or dmgbuild if available, or hdiutil as native fallback.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def clean_build_dirs():
    """Remove build and dist folders if they exist to ensure a clean build."""
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Removing existing '{folder}' directory...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Warning: Could not remove '{folder}' folder: {e}")


def build_mac_app():
    """Compile PrivacyScribe into a standalone macOS .app bundle using PyInstaller."""
    print("Starting Privacy Scribe macOS .app build process...")
    clean_build_dirs()

    spec_path = "scribe-dictation-mac.spec"
    if not os.path.exists(spec_path):
        print(f"Error: Specification file '{spec_path}' not found!")
        sys.exit(1)

    command = ["uv", "run", "pyinstaller", "--clean", spec_path]
    print(f"Executing: {' '.join(command)}")

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller build failed: {e}")
        sys.exit(1)

    app_path = Path("dist/PrivacyScribe.app")
    if not app_path.exists():
        print(f"Error: Expected app bundle at '{app_path}' was not generated!")
        sys.exit(1)

    print(f"\nSuccessfully built macOS App bundle at: {app_path.resolve()}")
    return app_path


def package_dmg(app_path: Path, dmg_name: str = "PrivacyScribe-0.2.0.dmg"):
    """Package the .app bundle into a DMG disk image."""
    dist_dir = Path("dist")
    dmg_path = dist_dir / dmg_name

    # Check for create-dmg CLI
    if shutil.which("create-dmg"):
        print(f"Packaging DMG using create-dmg -> {dmg_path}...")
        cmd = [
            "create-dmg",
            "--volname",
            "Privacy Scribe Installer",
            "--window-pos",
            "200",
            "120",
            "--window-size",
            "600",
            "400",
            "--icon-size",
            "100",
            "--icon",
            "PrivacyScribe.app",
            "160",
            "190",
            "--hide-extension",
            "PrivacyScribe.app",
            "--app-drop-link",
            "440",
            "190",
            str(dmg_path),
            str(app_path),
        ]
        try:
            subprocess.run(cmd, check=True)
            print(f"\nDMG packaging complete: {dmg_path.resolve()}")
            return dmg_path
        except subprocess.CalledProcessError as e:
            print(f"create-dmg failed: {e}. Falling back to hdiutil/dmgbuild...")

    # Check for dmgbuild Python module
    try:
        import dmgbuild

        print(f"Packaging DMG using dmgbuild -> {dmg_path}...")
        settings = {
            "volume_name": "Privacy Scribe",
            "format": "UDZO",
            "files": [str(app_path)],
            "symlinks": {"Applications": "/Applications"},
            "badge_icon": "scribe_dictation/resources/icon.png",
        }

        dmgbuild.build_dmg(str(dmg_path), "Privacy Scribe", settings=settings)
        print(f"\nDMG packaging complete with dmgbuild: {dmg_path.resolve()}")
        return dmg_path
    except ImportError:
        pass

    # Native macOS fallback using hdiutil
    if platform.system() == "Darwin" and shutil.which("hdiutil"):
        print(f"Packaging DMG using native macOS hdiutil -> {dmg_path}...")
        cmd = [
            "hdiutil",
            "create",
            "-volname",
            "Privacy Scribe",
            "-srcfolder",
            str(app_path),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
        try:
            subprocess.run(cmd, check=True)
            print(f"\nDMG packaging complete with hdiutil: {dmg_path.resolve()}")
            return dmg_path
        except subprocess.CalledProcessError as e:
            print(f"hdiutil failed: {e}")
            sys.exit(1)

    print(
        "Notice: DMG creation skipped (create-dmg/dmgbuild/hdiutil not available). .app bundle is preserved in dist/"
    )
    return app_path


def main():
    if platform.system() != "Darwin":
        print(
            f"Note: Running build_mac.py on {platform.system()}. macOS bundles and DMGs are typically built on macOS runners."
        )

    app_path = build_mac_app()
    package_dmg(app_path)
    print("\n" + "=" * 50)
    print("MACOS PACKAGING PROCESS COMPLETED SUCCESSFULLY")
    print("=" * 50)


if __name__ == "__main__":
    main()
