from web.app import app

def get_status():
    """
    Returns the current status of the daemon.
    This function can later be updated to fetch the status
    from a socket, subprocess, or external service.
    """
    daemon = getattr(app.state, 'daemon', None)
    if daemon is None:
        return {"error": "Daemon state not available"}
    return daemon.as_dict()