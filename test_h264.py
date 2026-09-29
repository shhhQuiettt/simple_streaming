import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

pipeline = Gst.parse_launch("ximagesrc xid=0 use-damage=0 ! video/x-raw,framerate=30/1 ! videoconvert ! queue max-size-buffers=1 leaky=downstream ! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=2500 ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! fakesink")
print("Pipeline valid")
