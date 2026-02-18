import subprocess
import sys
from pathlib import Path

def main():
    # Program entry point: Streamlit only.
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("Streamlit is not installed. Install it and run the app again.")
        return

    app_path = Path(__file__).with_name("streamlit_app.py")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
        ],
        check=False,
    )
    if result.returncode != 0:
        print("Streamlit failed to launch.")


if __name__ == "__main__":
    main()
