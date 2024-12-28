#!/usr/bin/env python

from flask import Flask, jsonify, request
import subprocess

app = Flask(__name__)

@app.route('/')
def index():
    return "Hello from PaperPi Web Interface!"

@app.route('/start_daemon', methods=['POST'])
def start_daemon():
    """
    Calls the daemon script with the "start" command.
    In a real environment, you'd rely on systemd:
      subprocess.run(["sudo", "systemctl", "start", "paperpi"])
    """
    subprocess.Popen(["python3.11", "paperpi_daemon.py", "start"])
    return jsonify({"status": "daemon start command issued"})

@app.route('/stop_daemon', methods=['POST'])
def stop_daemon():
    """
    Calls the daemon script with the "stop" command.
    This won't actually kill a foreground daemon unless
    you have a background process + PID file logic.
    """
    subprocess.run(["python3.11", "paperpi_daemon.py", "stop"])
    return jsonify({"status": "daemon stop command issued"})

@app.route('/daemon_status', methods=['GET'])
def daemon_status():
    """
    Calls the script with "status". We only log a message in
    the daemon script, so we can't get real status back here.
    In production, you'd check systemd or parse logs.
    """
    output = subprocess.run(["python3.11", "paperpi_daemon.py", "status"], capture_output=True, text=True)
    return jsonify({"daemon_status": output.stdout})

if __name__ == '__main__':
    # For dev/demo. In production, you’d run behind gunicorn or systemd.
    app.run(host='0.0.0.0', port=5000, debug=True)
