from pythonosc.udp_client import SimpleUDPClient
import socket
import json

# Request plugin list to see what's available
client = SimpleUDPClient('127.0.0.1', 11002)
client.send_message('/jarvis/plugins/get', ['audio_effect', 0, 100])
print('Requested audio_effect plugins...')

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.settimeout(10.0)
sock.bind(('127.0.0.1', 11003))
try:
    data, addr = sock.recvfrom(65535)
    print(f'Response length: {len(data)} bytes')
    
    # The response format is: [success, status, total, offset, limit, json_string]
    # We need to extract the JSON part at the end
    # Find the last occurrence of '[' which starts the JSON array
    data_str = data.decode('utf-8', errors='ignore')
    
    # Look for the JSON array
    json_start = data_str.rfind('[{')
    if json_start > 0:
        json_str = data_str[json_start:].rstrip('\x00')
        plugins = json.loads(json_str)
        print(f'Found {len(plugins)} audio effects')
        
        # Look for EQ Eight specifically
        eq_eight = [p for p in plugins if 'eq eight' in p.get('name', '').lower()]
        print(f'\nEQ Eight matches: {eq_eight}')
        
        # Show all native devices
        native = [p for p in plugins if p.get('is_native')]
        print(f'\nNative devices found: {len(native)}')
        for p in native[:20]:
            print(f"  - {p.get('name')}")
            
        # Show first 20 overall
        print(f'\nFirst 20 audio effects:')
        for p in plugins[:20]:
            print(f"  - {p.get('name')} (native={p.get('is_native', False)}, loadable={p.get('loadable', '?')})")
    else:
        print(f'Could not parse response: {data_str[:500]}')
        
except socket.timeout:
    print('No response (timeout)')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
sock.close()
