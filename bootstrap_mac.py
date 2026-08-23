import os
import urllib.request
import json
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk
import threading

GITHUB_REPO = "subtiliorars-sys/scribe-dictation"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
LATEST_RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


class BootstrapAppMac:
    def __init__(self, root):
        self.root = root
        self.root.title("Privacy Scribe Installer")
        self.root.geometry("420x160")
        self.root.resizable(False, False)

        # Apply basic styling
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.label = ttk.Label(
            root,
            text="Initializing Privacy Scribe Downloader...",
            font=("Helvetica", 10),
            wraplength=380,
        )
        self.label.pack(pady=20, padx=20)

        self.progress = ttk.Progressbar(
            root, orient="horizontal", length=360, mode="determinate"
        )
        self.progress.pack(pady=10, padx=20)

        # Run bootstrap logic in background thread
        threading.Thread(target=self.run_bootstrap, daemon=True).start()

    def update_status(self, text, value=None):
        self.root.after(0, lambda: self.label.config(text=text))
        if value is not None:
            self.root.after(0, lambda: self.progress.config(value=value))

    def run_bootstrap(self):
        try:
            self.update_status("Checking GitHub for the latest version...")
            req = urllib.request.Request(
                LATEST_RELEASE_API,
                headers={"User-Agent": "PrivacyScribe-Bootstrap-Mac/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch metadata (HTTP {resp.status})")
                data = json.loads(resp.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            download_url = ""
            for asset in data.get("assets", []):
                asset_name = asset.get("name", "")
                if asset_name.endswith(".dmg") and "launcher" not in asset_name.lower():
                    download_url = asset.get("browser_download_url", "")
                    break

            if not download_url:
                raise Exception(
                    "macOS DMG asset not found in the latest release assets."
                )

            self.update_status(f"Downloading Privacy Scribe {tag_name}...")

            temp_dir = tempfile.gettempdir()
            dmg_path = os.path.join(temp_dir, f"PrivacyScribe-{tag_name}.dmg")

            # Download file with progress updates
            req = urllib.request.Request(
                download_url, headers={"User-Agent": "PrivacyScribe-Bootstrap-Mac/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60.0) as response:
                total_size = int(response.info().get("Content-Length", 0))
                bytes_downloaded = 0
                block_size = 65536

                with open(dmg_path, "wb") as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        bytes_downloaded += len(buffer)
                        f.write(buffer)
                        if total_size > 0:
                            percent = (bytes_downloaded / total_size) * 100
                            self.update_status(
                                f"Downloading Privacy Scribe {tag_name}... {percent:.1f}%",
                                percent,
                            )

            self.update_status("Mounting DMG installer...")
            # Mount the DMG
            subprocess.run(["hdiutil", "mount", dmg_path], check=True)

            # Find and open mounted volume in Finder
            mount_points = [
                "/Volumes/Privacy Scribe",
                "/Volumes/Privacy Scribe Installer",
            ]
            opened = False
            for mp in mount_points:
                if os.path.exists(mp):
                    subprocess.Popen(["open", mp])
                    opened = True
                    break
            if not opened:
                subprocess.Popen(["open", "/Volumes"])

            import time

            time.sleep(0.5)
            self.root.after(0, self.root.destroy)

        except Exception as e:
            self.update_status(f"Error during installation: {e}", 0)
            self.root.after(0, self.add_close_button)

    def add_close_button(self):
        close_btn = ttk.Button(self.root, text="Close", command=self.root.destroy)
        close_btn.pack(pady=10)


def main():
    root = tk.Tk()
    root.config(padx=10, pady=10)
    BootstrapAppMac(root)
    root.mainloop()


if __name__ == "__main__":
    main()
