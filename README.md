# Low-Latency X11 Window Streamer over WebRTC

This project captures a specific X11 window based on its title and streams it with very low latency over the local network using WebRTC.

## Architecture

The system consists of two parts:

1. **Python Server** (`server/server.py`):
   - Uses `wmctrl` to discover the X11 window ID from a title substring.
   - Sets up a GStreamer pipeline using `ximagesrc` for capture and `webrtcbin` for streaming.
   - Hosts a WebSocket server (`websockets`) on port 8081 for WebRTC signaling (SDP/ICE exchange).
   - Encodes the video. By default, it uses software encoding (`vp8enc`) for maximum WebRTC compatibility and simplicity, optimized for zero latency.

2. **Web Client** (`client/`):
   - A plain HTML/CSS/JS frontend served via Python's built-in `http.server` on port 8080.
   - Connects to the WebSocket signaling server and establishes a WebRTC PeerConnection to receive the video stream.

Because both run on the local LAN, there is no need for STUN/TURN servers or complex signaling infrastructure.

## Dependencies

### Normal Linux Machine (Development)
You need GStreamer, its Python bindings, X11 utilities, and `uv` for dependency management.

On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y \
    python3-gi gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly wmctrl curl

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Arch Linux:
```bash
sudo pacman -S uv gst-python gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly wmctrl
```

## Usage

### 1. Start the Server
Provide a substring of the title of the window you want to capture.

```bash
chmod +x run-server.sh
./run-server.sh "brave"
```
The server will find the window and start listening for WebRTC connections on `ws://0.0.0.0:8081`.

### 2. Start the Client
```bash
chmod +x run-client.sh
./run-client.sh
```
This will start a web server on `http://localhost:8080`.

### 3. View the Stream
Open your browser (Firefox or Chrome) and navigate to `http://localhost:8080`.
The video should connect and autoplay.

## Upgrading to Jetson Hardware Encoding

The pipeline in `server/server.py` is modular. The software VP8 encoder is currently active. 

To switch to NVIDIA Jetson AGX Orin hardware encoding:
1. Ensure the `nvvideo4linux2` GStreamer plugin is installed (comes with JetPack).
2. Open `server/server.py`.
3. Locate the `create_pipeline_string()` function.
4. Replace the `encoder` variable with:
   ```python
   encoder = "nvvidconv ! nvv4l2h264enc insert-sps-pps=true maxperf-enable=true bitrate=2500000 ! rtph264pay"
   ```
5. Update the payload in the `caps` variable to H264:
   ```python
   caps = "application/x-rtp,media=video,encoding-name=H264,payload=96"
   ```

## Limitations & Considerations
- **Wayland**: This tool uses `ximagesrc` and `wmctrl`, which are strictly for X11. Wayland window capture requires entirely different mechanisms (like PipeWire and xdg-desktop-portal).
- **Occlusion**: `ximagesrc` generally captures what is visible on the screen. If the window is covered by another window, the covering window might be recorded depending on the X server composite manager setup (the `use-damage=0` property tries to help, but behavior varies by compositor).
- **Audio**: This is a video-only pipeline.
