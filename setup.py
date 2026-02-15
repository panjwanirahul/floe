"""Floe - Launch the setup/dashboard web UI."""

import os
import shutil
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / "config" / ".env"
ENV_EXAMPLE = ROOT / "config" / ".env.example"


def preflight():
    """Validate config before launching the web UI."""
    if not ENV_PATH.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_PATH)
            print("\n  Created config/.env from template.")
            print("  Edit it with your API keys, then re-run.\n")
            sys.exit(0)
        else:
            print("  ERROR: config/.env.example not found.")
            sys.exit(1)

    load_dotenv(str(ENV_PATH))

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        print("\n  Set your ANTHROPIC_API_KEY in config/.env\n")
        sys.exit(1)

    auth_file = os.getenv("YTMUSIC_AUTH_FILE", "./config/headers_auth.json")
    auth_path = ROOT / auth_file if not Path(auth_file).is_absolute() else Path(auth_file)
    if not auth_path.exists():
        print(f"\n  YT Music auth not found at: {auth_path}")
        print("  Run: ytmusicapi oauth")
        print("  Then move the file to config/headers_auth.json\n")
        sys.exit(1)

    print("  [OK] Config validated")


def main():
    print("\n  === Floe ===\n")
    preflight()

    from src.app import app

    port = int(os.getenv("FLOE_PORT", "5050"))
    Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    print(f"  Starting at http://localhost:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
