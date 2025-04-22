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
from fastapi import FastAPI
from web.routes import base  # import your routes

app = FastAPI()

# Include routes
app.include_router(base.router)

# +
# ###############################################################################
# # FLASK WEB SERVER
# ###############################################################################

# app = Flask(__name__)

# # We'll store a flag indicating the daemon loop is running
# daemon_running = True
# # We'll also detect if we're in systemd mode or foreground
# systemd_mode = running_under_systemd()

# @app.route('/')
# def home():
#     return """
#     <h1>Welcome to PaperPi</h1>
#     <p>Stub login page or config interface will go here.</p>
#     <p>Try POSTing to /stop to halt the daemon.</p>
#     """

# @app.route('/login')
# def login():
#     # Stub route for future authentication implementation
#     return "Login page (to be implemented)."

# @app.route('/stop', methods=['POST'])
# def stop_route():
#     """
#     A web endpoint to stop the daemon thread (and Flask).
#     In systemd mode, the service will stop in the background.
#     In foreground mode, we print 'stopped: press ctrl+c to exit.'
#     """
#     global daemon_running
#     daemon_running = False
#     logger.info("Received /stop request; shutting down daemon and Flask...")

#     # Ask Flask's built-in server to shut down
#     shutdown_server()

#     if not systemd_mode:
#         # In foreground mode, let the user know they can Ctrl+C
#         logger.info("stopped: press ctrl+c to exit")

#     return jsonify({"message": "Stopping daemon..."})

# def shutdown_server():
#     """
#     Trigger a shutdown of the built-in Werkzeug server.
#     """
#     func = request.environ.get('werkzeug.server.shutdown')
#     if func is None:
#         logger.warning("Not running with the Werkzeug Server, can't shut down cleanly.")
#     else:
#         func()
