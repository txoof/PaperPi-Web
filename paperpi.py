#! /usr/env/python
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
import threading
import queue
import time
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys


class PaperPiDaemon:
    def __init__(self, heartbeat_interval=10):
        self.running = False
        self.command_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.heartbeat_interval = heartbeat_interval
        self.condition = threading.Condition()  # Condition variable for waiting
        self.setup_logging()
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def setup_logging(self):
        self.logger = logging.getLogger("PaperPiDaemon")
        
        # Prevent adding multiple handlers
        if not self.logger.hasHandlers():
            log_handler = RotatingFileHandler(
                "paperpi_daemon.log", maxBytes=1000000, backupCount=3
            )
            log_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )
            log_handler.setFormatter(log_formatter)
            self.logger.setLevel(logging.DEBUG)
            self.logger.addHandler(log_handler)
            self.logger.debug("Daemon initialized (debug mode).")
        else:
            self.logger.debug("Logger already initialized, skipping handler setup.")

    def start(self):
        with self.condition:  # Acquire condition lock
            if not self.running:
                self.running = True
                self.logger.info("Daemon started.")
                self.condition.notify()  # Wake up the loop
            else:
                self.logger.warning("Start request received, but daemon is already running.")

    def stop(self):
        with self.condition:  # Acquire condition lock
            if self.running:
                self.running = False
                self.logger.info("Daemon stopping...")
                self.stop_event.set()
                self.condition.notify()  # Wake up to exit loop
            else:
                self.logger.warning("Stop request received, but daemon is not running.")

    def handle_command(self, command):
        if command == "start":
            self.start()
        elif command == "stop":
            self.stop()
        else:
            self.logger.error(f"Unknown command received: {command}")

    def command_listener(self):
        while not self.stop_event.is_set():
            try:
                command = self.command_queue.get(timeout=1)
                self.handle_command(command)
            except queue.Empty:
                pass
    
    def heartbeat(self):
        while not self.stop_event.is_set():
            self.logger.debug("Heartbeat thread active.")
            if self.running:
                self.logger.info("Heartbeat: Daemon is running.")
            time.sleep(self.heartbeat_interval)
            
    def run(self):
        listener_thread = threading.Thread(target=self.command_listener, daemon=True)
        listener_thread.start()
        
        heartbeat_thread = threading.Thread(target=self.heartbeat, daemon=True)
        heartbeat_thread.start()

        self.logger.info("Daemon loop running...")

        try:
            while not self.stop_event.is_set():
                with self.condition:  # Efficient wait
                    if self.running:
                        self.logger.info("Updating e-paper display...")
                    self.condition.wait(timeout=5)  # Wait for signal or timeout
        except KeyboardInterrupt:
            self.logger.info("Interrupt received, stopping daemon...")

        self.logger.info("Daemon loop exited.")

    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)  # Force kernel to stop all threads


# -

if __name__ == "__main__":
    daemon = PaperPiDaemon(heartbeat_interval=10)
    daemon.run()


