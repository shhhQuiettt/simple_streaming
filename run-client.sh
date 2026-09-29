#!/bin/bash

# Exit on error
set -e

PORT=8080

echo "Starting HTTP server for the client on http://localhost:${PORT}"
echo "Open this URL in your web browser."

cd client
python3 -m http.server ${PORT}
