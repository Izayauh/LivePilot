# JarvisDeviceLoader - Ableton Live Remote Script

This Remote Script extends Ableton Live's capabilities to support loading devices/plugins
via OSC commands from Jarvis.

## Installation

1. Copy the `JarvisDeviceLoader` folder to your Ableton MIDI Remote Scripts directory:

   **Windows:**
   ```
   C:\ProgramData\Ableton\Live 11\Resources\MIDI Remote Scripts\JarvisDeviceLoader
   ```

   **Mac:**
   ```
   /Applications/Ableton Live 11 Suite.app/Contents/App-Resources/MIDI Remote Scripts/JarvisDeviceLoader
   ```

2. Open Ableton Live

3. Go to **Preferences > Link/Tempo/MIDI > Control Surface**

4. Select **JarvisDeviceLoader** from the dropdown menu

5. The script will start listening for OSC commands on port 11002

## Features

- Load devices/plugins by name onto any track
- Query available plugins from Ableton's browser
- Delete devices from tracks
- Cache plugin list for fast lookups

## OSC Commands

The script listens on port **11002** and sends responses to port **11003**.

| Address | Arguments | Description |
|---------|-----------|-------------|
| `/jarvis/device/load` | track_index, device_name, [position] | Load a device onto a track |
| `/jarvis/plugins/get` | [category] | Get list of available plugins |
| `/jarvis/plugins/refresh` | - | Force refresh plugin cache |
| `/jarvis/device/delete` | track_index, device_index | Delete a device |
| `/jarvis/test` | - | Test connection |

## Voice Commands

Once installed, you can use these voice commands with Jarvis:

- "Add EQ Eight to track 1"
- "Add FabFilter Pro-Q to track 2"
- "Create a Billie Eilish vocal chain on track 1"
- "Load a basic vocal preset on track 3"
- "What compressors do I have?"

## Troubleshooting

### Script not appearing in preferences
- Make sure the folder is named exactly `JarvisDeviceLoader`
- Ensure `__init__.py` is directly inside the folder
- Restart Ableton Live

### Commands not working
- Check Ableton's Log.txt for errors
- Ensure no other application is using ports 11002/11003
- Verify the script is selected in Ableton preferences

### Plugin not found
- Try refreshing the plugin list: "Refresh the plugin list"
- Use the exact plugin name as shown in Ableton
- Check if the plugin is installed and scanned

## Log Location

Ableton's log file contains JarvisDeviceLoader messages:

**Windows:**
```
C:\Users\[Username]\AppData\Roaming\Ableton\Live 11.x\Preferences\Log.txt
```

**Mac:**
```
/Users/[Username]/Library/Preferences/Ableton/Live 11.x/Log.txt
```

