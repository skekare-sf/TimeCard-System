"""Run the Timecard Management System web app."""
import webbrowser
import threading
import time
from app import app


def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    print("\n" + "=" * 60)
    print("  TIMECARD MANAGEMENT SYSTEM")
    print("  Open: http://localhost:5000")
    print("  Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    app.run(port=5000, debug=False, use_reloader=False)
