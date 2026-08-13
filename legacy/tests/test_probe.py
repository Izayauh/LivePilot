from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading
import time

# Configuration
SEND_PORT = 11000
LISTEN_PORT = 11001
TRACK_IDX = 0

def debug_handler(address, *args):
    print(f"OSC MSG: {address} | ARGS: {args}")

def probe_osc():
    print("--- OSC PROBE ---")
    dispatcher = Dispatcher()
    dispatcher.set_default_handler(debug_handler)
    
    server = BlockingOSCUDPServer(("127.0.0.1", LISTEN_PORT), dispatcher)
    st = threading.Thread(target=server.serve_forever)
    st.daemon = True
    st.start()
    
    client = SimpleUDPClient("127.0.0.1", SEND_PORT)
    
    print("Sending /live/track/get/devices/name [0, 0]...")
    client.send_message("/live/track/get/devices/name", [0, 0])
    time.sleep(0.5)
    
    print("Sending /live/track/get/devices/name [0, 1]...")
    client.send_message("/live/track/get/devices/name", [0, 1])
    time.sleep(0.5)

    server.shutdown()
    st.join()

if __name__ == "__main__":
    probe_osc()
