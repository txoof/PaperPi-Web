

# PaperPi Daemon HTTP API

Internal daemon API Documentation

## GET /config/app

Returns the current application configuration as JSON.

**Example:**
```bash
curl http://localhost:2822/config/app
```

**Response:**
```json
{
  "display_type": "epd7in5_V2",
  "log_level": "DEBUG",
  "refresh_interval": 5
}
```


## GET /shutdown

Triggers a graceful shutdown of the PaperPi daemon and main process.

**Intended for internal use.**

**Example:**
```bash
curl http://localhost:2822/shutdown
```

**Response:**
```json
{ "status": "shutting down" }
```