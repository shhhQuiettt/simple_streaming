import sys
import os
import subprocess
import json
import asyncio
import threading
import websockets
import logging

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc-server")

import argparse

# -------------------------------------------------------------------------
# X11 Window Discovery
# -------------------------------------------------------------------------
def find_window_id(title_substring):
    try:
        # wmctrl -l format: "0x0080001e  1 KRZYS-ARCH AGENTS.md - Brave"
        output = subprocess.check_output(['wmctrl', '-l']).decode('utf-8')
        for line in output.splitlines():
            parts = line.split(maxsplit=3)
            if len(parts) >= 4:
                win_id_hex = parts[0]
                win_title = parts[3]
                if title_substring.lower() in win_title.lower():
                    logger.info(f"Found window: {win_title}")
                    return int(win_id_hex, 16)
    except Exception as e:
        logger.error(f"Failed to find window: {e}")
    return None

# -------------------------------------------------------------------------
# GStreamer Pipeline Configuration
# -------------------------------------------------------------------------
def create_pipeline_string(xid, codec="h264"):
    """
    Creates the GStreamer pipeline string for capturing an X11 window.
    """
    
    # 1. Capture stage
    capture = f"ximagesrc xid={xid} use-damage=0 ! video/x-raw,framerate=30/1 ! videoconvert ! queue max-size-buffers=1 leaky=downstream"
    
    if codec == "h265":
        encoder = "x265enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=2500 ! rtph265pay config-interval=-1 aggregate-mode=zero-latency"
        caps = "application/x-rtp,media=video,encoding-name=H265,payload=96"
    else:
        # 2. Encoder stage (Software H.264 - zero latency preset)
        encoder = "x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=2500 ! rtph264pay config-interval=-1 aggregate-mode=zero-latency"
        # 3. Payload format (Matches the encoder output)
        caps = "application/x-rtp,media=video,encoding-name=H264,payload=96"
    
    # Complete pipeline
    return f"{capture} ! {encoder} ! {caps} ! webrtcbin name=webrtcbin"

# -------------------------------------------------------------------------
# WebRTC Session Manager
# -------------------------------------------------------------------------
class WebRTCClientSession:
    def __init__(self, websocket, window_id, loop, codec):
        self.ws = websocket
        self.window_id = window_id
        self.loop = loop
        self.codec = codec
        self.pipeline = None
        self.webrtcbin = None

    def start(self):
        pipeline_str = create_pipeline_string(self.window_id, self.codec)
        logger.info(f"Starting pipeline: {pipeline_str}")
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.webrtcbin = self.pipeline.get_by_name('webrtcbin')

        # Connect signals
        self.webrtcbin.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtcbin.connect('on-ice-candidate', self.on_ice_candidate)

        self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

    def on_negotiation_needed(self, element):
        logger.info("Negotiation needed, creating offer...")
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def on_offer_created(self, promise, element, _):
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        
        local_desc_promise = Gst.Promise.new()
        element.emit('set-local-description', offer, local_desc_promise)

        # Send offer to client
        text = offer.sdp.as_text()
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({'sdp': {'type': 'offer', 'sdp': text}})),
            self.loop
        )

    def on_ice_candidate(self, element, mlineindex, candidate):
        logger.info(f"Local ICE candidate: {candidate}")
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({
                'ice': {
                    'sdpMLineIndex': mlineindex,
                    'candidate': candidate
                }
            })),
            self.loop
        )

    def handle_sdp(self, sdp_dict):
        type_ = sdp_dict.get('type')
        sdp_text = sdp_dict.get('sdp')
        if type_ == 'answer':
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp_text.encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtcbin.emit('set-remote-description', answer, promise)
            logger.info("Applied remote answer")

    def handle_ice(self, ice_dict):
        candidate = ice_dict.get('candidate')
        sdpmlineindex = ice_dict.get('sdpMLineIndex')
        if candidate:
            self.webrtcbin.emit('add-ice-candidate', sdpmlineindex, candidate)
            logger.info("Added remote ICE candidate")

# -------------------------------------------------------------------------
# WebSocket Signaling Server
# -------------------------------------------------------------------------
clients = set()
window_id_target = None
main_loop = None
selected_codec = "h264"

async def signaling_handler(websocket):
    logger.info("Viewer connected")
    clients.add(websocket)
    session = WebRTCClientSession(websocket, window_id_target, main_loop, selected_codec)
    session.start()

    try:
        async for message in websocket:
            data = json.loads(message)
            if 'sdp' in data:
                session.handle_sdp(data['sdp'])
            elif 'ice' in data:
                session.handle_ice(data['ice'])
    except websockets.ConnectionClosed:
        logger.info("Viewer disconnected")
    finally:
        session.stop()
        clients.remove(websocket)

def run_glib_mainloop():
    loop = GLib.MainLoop()
    loop.run()

async def run_server(host, port):
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    async with websockets.serve(signaling_handler, host, port):
        print(f"\nSignalling server listening on ws://{host}:{port}")
        print("Waiting for WebRTC client...")
        await asyncio.Future()  # run forever

def main():
    global window_id_target, selected_codec
    
    parser = argparse.ArgumentParser(description="X11 Window WebRTC Streamer")
    parser.add_argument("title", help="Substring of the window title to match")
    parser.add_argument("--codec", choices=["h264", "h265"], default="h264", help="Video codec to use (default: h264)")
    args = parser.parse_args()

    target_title = args.title
    selected_codec = args.codec
    
    Gst.init(None)
    
    # Start GLib MainLoop in a separate thread for GStreamer events
    glib_thread = threading.Thread(target=run_glib_mainloop, daemon=True)
    glib_thread.start()

    print(f"Searching for window containing: {target_title}")
    window_id_target = find_window_id(target_title)
    
    if window_id_target is None:
        print(f"Error: Window matching '{target_title}' not found.")
        sys.exit(1)
        
    print(f"Window ID: {hex(window_id_target)}")
    
    try:
        asyncio.run(run_server('0.0.0.0', 8081))
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == '__main__':
    main()
