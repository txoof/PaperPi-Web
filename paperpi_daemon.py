#! /usr/bin/env python
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.4
#   kernelspec:
#     display_name: Python (PaperPi-Web-venv-33529be2c6)
#     language: python
#     name: paperpi-web-venv-33529be2c6
# ---

# +
# #!/usr/bin/env python3
import sys
import time
import logging
import signal
import os

PID_FILE = "/tmp/paperpi_daemon.pid"
running = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def write_pid_file():
    """Write the current process ID to the PID_FILE."""
    pid = os.getpid()
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

def remove_pid_file():
    """Remove the PID file if it exists."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

def signal_handler(sig, frame):
    global running
    logging.info(f"Signal {sig} received. Stopping daemon...")
    running = False

def run_daemon():
    """Main loop of the daemon."""
    global running
    running = True

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Write our PID to a file so that 'stop' knows who to kill
    write_pid_file()
    logging.info("Daemon started. Press Ctrl+C to stop or call `stop` command.")

    try:
        while running:
            logging.info("Daemon is working (e.g. updating e-paper).")
            time.sleep(5)
    finally:
        # Clean up the PID file on exit
        remove_pid_file()
        logging.info("Daemon stopped.")

def start_daemon():
    """Check if already running, else start a new daemon process."""
    if os.path.exists(PID_FILE):
        # If there's a PID file, the daemon might be running
        print("Daemon may already be running. Check status or remove PID file.")
        sys.exit(1)

    # Start the daemon (foreground). In production, you might daemonize or rely on systemd.
    run_daemon()

def stop_daemon():
    """Stop the running daemon by reading its PID file and sending a signal."""
    if not os.path.exists(PID_FILE):
        print("No PID file found. Daemon is not running or PID file is missing.")
        return

    # Read the PID
    with open(PID_FILE, "r") as f:
        pid_str = f.read().strip()
    pid = int(pid_str)

    logging.info(f"Stopping daemon with PID {pid}.")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("Process not found. Removing stale PID file.")
        remove_pid_file()

def get_status():
    """Check if the daemon is running by checking the PID file and process."""
    if not os.path.exists(PID_FILE):
        print("Daemon is not running.")
        return

    with open(PID_FILE, "r") as f:
        pid_str = f.read().strip()
    pid = int(pid_str)

    # Check if process is alive
    try:
        os.kill(pid, 0)  # 0 doesn't send a signal, but checks if process exists
        print(f"Daemon is running with PID {pid}.")
    except ProcessLookupError:
        print("PID file exists but process is not running. Remove the PID file.")

def main():
    if len(sys.argv) < 2:
        print("Usage: paperpi_daemon.py [start|stop|status|restart]")
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "start":
        start_daemon()
    elif command == "stop":
        stop_daemon()
    elif command == "status":
        get_status()
    elif command == "restart":
        stop_daemon()
        start_daemon()
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
