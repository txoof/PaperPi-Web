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
###############################################################################
# DAEMON LOOP
###############################################################################

def daemon_loop():
    """
    The background thread that handles e-paper updates.
    It runs until daemon_running = False.
    """
    logger.info("Daemon loop started.")
    while daemon_running:
        logger.info("display update goes here")
        logger.info('morestuff')
        # In production, you might call a function to update the display here
        time.sleep(5)
    logger.info("Daemon loop stopped.")


# from IPython.display import display, clear_output

# current_image_hash = ''
# plugin_manager.update_cycle()
# try:
#     while True:
#         if current_image_hash != plugin_manager.foreground_plugin.image_hash:
#             current_image_hash = plugin_manager.foreground_plugin.image_hash
#             clear_output(wait=True)        
#             display(plugin_manager.foreground_plugin.image)

#         time.sleep(5)
#         plugin_manager.update_cycle()
# except KeyboardInterrupt:
#     logger.info("Stopped update loop")    
# -

def handle_signal(signum, frame):
    """
    Handle SIGINT (Ctrl+C) or SIGTERM (systemctl stop) for a graceful shutdown:
      - Stop the daemon loop
      - Shut down Flask if possible
    """
    logger.info(f"Signal {signum} received, initiating shutdown.")
    global daemon_running
    daemon_running = False

    
    # shtudown web server here
    try:
        pass # shutdown 
    except Exception as e:
        logger.debug(f"Exception while shutting down Flask: {e}")

    # If running in the foreground, user can also press Ctrl+C again, but let's exit gracefully
    sys.exit(0)

