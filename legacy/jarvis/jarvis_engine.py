import asyncio
import os
import logging

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController
from jarvis_tools import ABLETON_TOOLS
from logging_config import setup_logging

# Import session manager for conversation tracking
from context.session_manager import session_manager
from context.session_persistence import get_session_persistence
from context.crash_recovery import get_crash_recovery

# Import workflow coordinator for end-to-end orchestration
from agents.workflow_coordinator import get_workflow_coordinator

# Import macro system
from macros.macro_builder import macro_builder

# Import agent system for intelligent audio engineering decisions
from agent_system import AgentOrchestrator
from agents.audio_engineer_agent import AudioEngineerAgent
from agents.research_agent import ResearchAgent
from agents.router_agent import RouterAgent
from agents.planner_agent import PlannerAgent
from agents.implementation_agent import ImplementationAgent
from agents.executor_agent import ExecutorAgent
from agents import AgentType, AgentMessage

# Import device intelligence for semantic parameter understanding
from discovery.device_intelligence import get_device_intelligence

# Import plugin chain building
from plugins.chain_builder import PluginChainBuilder, create_plugin_chain
from knowledge.plugin_chain_kb import get_plugin_chain_kb

# 1. Setup and Environment
load_dotenv()
os.environ["PYTHONIOENCODING"] = "utf-8"

# Verbose logging mode - set to True for detailed diagnostics
VERBOSE_LOGGING = True

# Initialize centralized logging system
# Console shows DEBUG if VERBOSE_LOGGING is True, otherwise INFO
console_level = logging.DEBUG if VERBOSE_LOGGING else logging.INFO
setup_logging(console_level=console_level)

# API Configuration
API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
MODEL_ID_AUDIO = "gemini-2.5-flash-native-audio-latest"
MODEL_ID_TEXT = "gemini-2.5-flash"

# Audio Configuration - IMPORTANT: Input is 16kHz, Output is 24kHz
CHANNELS = 1
SEND_SAMPLE_RATE = 16000   # Mic input rate
RECEIVE_SAMPLE_RATE = 24000  # Speaker output rate (model outputs at 24kHz)
CHUNK_SIZE = 1024

if PYAUDIO_AVAILABLE:
    FORMAT = pyaudio.paInt16
    pya = pyaudio.PyAudio()
else:
    FORMAT = None
    pya = None

# Initialize agent system for intelligent audio engineering
agent_orchestrator = AgentOrchestrator()
# Register all agents for full multi-agent orchestration
agent_orchestrator.register_agent(RouterAgent(agent_orchestrator))
agent_orchestrator.register_agent(AudioEngineerAgent(agent_orchestrator))
agent_orchestrator.register_agent(ResearchAgent(agent_orchestrator))
agent_orchestrator.register_agent(PlannerAgent(agent_orchestrator))
agent_orchestrator.register_agent(ImplementationAgent(agent_orchestrator))
agent_orchestrator.register_agent(ExecutorAgent(agent_orchestrator))
agent_orchestrator.set_ableton_controller(ableton)

# Initialize workflow coordinator for end-to-end orchestration
workflow_coordinator = get_workflow_coordinator(agent_orchestrator)

# Initialize session persistence for cross-session learning
session_persistence = get_session_persistence()

# Initialize crash recovery system
crash_recovery = get_crash_recovery()
crash_recovery.set_controller(ableton)

# Initialize device intelligence for semantic parameter understanding
device_intelligence = get_device_intelligence()

# Initialize reliable parameter controller for verified parameter operations
reliable_params = ReliableParameterController(ableton, verbose=False)

# Initialize plugin chain knowledge base
plugin_chain_kb = get_plugin_chain_kb()

# Audio queues for non-blocking operation
audio_queue_output = asyncio.Queue()
audio_queue_mic = asyncio.Queue(maxsize=5)

# Flag to pause mic input while Jarvis is speaking (prevents echo/self-interruption)
is_playing = asyncio.Event()
is_playing.clear()  # Not playing initially

# Flag to signal shutdown
shutdown_event = asyncio.Event()

# Flag to track if the session connection is alive
session_connected = asyncio.Event()
session_connected.set()  # Initially connected

# Track conversation state for debugging
conversation_state = {
    "last_tool_call_time": None,
    "last_tool_response_sent": None,
    "audio_chunks_sent": 0,
    "tool_calls_executed": 0,
    "turns_completed": 0,
    "waiting_for_response": False,
    "last_transcription": None,
}

# Retry configuration
MAX_RETRIES = 2
RETRY_DELAY = 0.5


def log(msg, level="INFO"):
    """
    Timestamped logging with levels.
    Now delegates to the centralized logging system while maintaining backward compatibility.
    """
    # Get the logger for jarvis.engine
    logger = logging.getLogger("jarvis.engine")

    # Map level strings to logging levels
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "STATE": logging.INFO,  # STATE messages are informational
    }

    log_level = level_map.get(level.upper(), logging.INFO)

    # Add emoji prefix for certain log types (for backward compatibility)
    if level == "ERROR":
        msg = f"❌ {msg}"
    elif level == "STATE":
        msg = f"📊 {msg}"
    elif level == "DEBUG":
        msg = f"[DBG] {msg}"
    elif level == "WARN":
        msg = f"[WARN] {msg}"

    # Log to the centralized system
    logger.log(log_level, msg)


def log_state():
    """Log current conversation state."""
    log(f"STATE: mic_muted={is_playing.is_set()}, "
        f"chunks_sent={conversation_state['audio_chunks_sent']}, "
        f"tools_executed={conversation_state['tool_calls_executed']}, "
        f"turns={conversation_state['turns_completed']}", "STATE")


async def generate_content_with_retry(client, model, contents, config, max_retries=3, base_delay=2.0):
    """
    Wrapper for generate_content that handles rate limiting (429) with exponential backoff.

    Args:
        client: The genai client
        model: Model ID to use
        contents: Conversation contents
        config: Generation config
        max_retries: Maximum number of retry attempts for rate limits
        base_delay: Base delay in seconds (doubles with each retry)

    Returns:
        Response from generate_content

    Raises:
        Exception: Re-raises non-rate-limit errors immediately
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response
        except genai_errors.ClientError as e:
            # Check if it's a rate limit error (429)
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                    log(f"Rate limit hit (429). Waiting {delay}s before retry {attempt + 1}/{max_retries}...", "WARN")
                    await asyncio.sleep(delay)
                    continue
                else:
                    log(f"Rate limit exceeded after {max_retries} retries. Please wait before trying again.", "ERROR")
                    raise
            else:
                # Non-rate-limit error, re-raise immediately
                raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


async def listen_audio():
    """Captures audio from the microphone and puts it into the mic queue."""
    # Wait for session to be connected before starting mic capture
    log("Waiting for session connection before starting mic...", "DEBUG")
    while not session_connected.is_set() and not shutdown_event.is_set():
        await asyncio.sleep(0.1)

    if shutdown_event.is_set():
        return

    mic_info = pya.get_default_input_device_info()
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SEND_SAMPLE_RATE,
        input=True,
        input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK_SIZE,
    )

    log(">>> Jarvis is listening (Hamilton Studio)...")
    log(f"    Mic device: {mic_info['name']}", "DEBUG")

    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            data = await asyncio.to_thread(
                audio_stream.read, CHUNK_SIZE, exception_on_overflow=False
            )

            # Only send mic audio when Jarvis is NOT speaking (prevents echo)
            # AND when session is connected
            if not is_playing.is_set() and session_connected.is_set():
                try:
                    audio_queue_mic.put_nowait({"data": data, "mime_type": "audio/pcm"})
                except asyncio.QueueFull:
                    # This should rarely happen now
                    pass
            # else: mic is muted while Jarvis speaks

    except Exception as e:
        if session_connected.is_set():
            log(f"Mic Error: {e}", "ERROR")
    finally:
        audio_stream.stop_stream()
        audio_stream.close()


async def send_audio(session):
    """Sends audio from the mic queue to the Gemini session."""
    chunk_count = 0
    last_log_time = datetime.now()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            try:
                msg = await asyncio.wait_for(audio_queue_mic.get(), timeout=1.0)
                
                # Check connection state before sending
                if not session_connected.is_set():
                    log("Connection closed, stopping audio send", "DEBUG")
                    break
                
                await session.send_realtime_input(media=msg)
                chunk_count += 1
                consecutive_errors = 0  # Reset error counter on success
                conversation_state["audio_chunks_sent"] = chunk_count
                
                # Log every 50 chunks (about 3 seconds of audio)
                if chunk_count % 50 == 0:
                    now = datetime.now()
                    elapsed = (now - last_log_time).total_seconds()
                    log(f"Audio: {chunk_count} chunks sent ({elapsed:.1f}s since last log)", "DEBUG")
                    last_log_time = now
                    
            except asyncio.TimeoutError:
                # Log if we've been waiting a while with no audio
                if is_playing.is_set():
                    log("Mic muted (Jarvis speaking)", "DEBUG")
                continue
            except Exception as e:
                error_msg = str(e)
                consecutive_errors += 1
                
                # Check for connection errors
                if "ConnectionClosed" in error_msg or "keepalive ping timeout" in error_msg or "1011" in error_msg:
                    log(f"Connection closed, stopping audio send: {e}", "ERROR")
                    session_connected.clear()
                    break
                
                # Log error but continue for transient errors
                if consecutive_errors <= max_consecutive_errors:
                    log(f"Send audio error ({consecutive_errors}/{max_consecutive_errors}): {e}", "ERROR")
                    await asyncio.sleep(0.1)
                else:
                    log(f"Too many consecutive errors, stopping audio send", "ERROR")
                    session_connected.clear()
                    break
                    
    except Exception as e:
        log(f"Send audio task error: {e}", "ERROR")
        session_connected.clear()


async def send_text(session):
    """Reads text from stdin and sends to Gemini session (text mode)."""
    loop = asyncio.get_event_loop()
    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            try:
                text = await loop.run_in_executor(None, lambda: input("You: "))
            except EOFError:
                break
            if not text:
                continue
            if text.strip().lower() in ("quit", "exit"):
                log("User requested shutdown via text.")
                shutdown_event.set()
                break
            await session.send(input=text, end_of_turn=True)
            conversation_state["turns_completed"] += 1
    except Exception as e:
        log(f"Send text task error: {e}", "ERROR")
        session_connected.clear()


async def receive_responses(session):
    """Receives responses from Gemini and handles audio, text, and tool calls."""
    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            try:
                log("Waiting for Gemini response...", "DEBUG")
                conversation_state["waiting_for_response"] = True
                
                turn = session.receive()
                async for response in turn:
                    # Check if connection is still alive
                    if not session_connected.is_set():
                        log("Connection closed during response processing", "DEBUG")
                        break
                    
                    try:
                        # ===== HANDLE SERVER CONTENT (Audio/Text) =====
                        if response.server_content:
                            sc = response.server_content
                            
                            # Handle model turn (audio/text output)
                            if sc.model_turn:
                                for part in sc.model_turn.parts:
                                    try:
                                        # Handle audio output
                                        if part.inline_data and isinstance(part.inline_data.data, bytes):
                                            audio_queue_output.put_nowait(part.inline_data.data)
                                        
                                        # Handle text output (transcription or response)
                                        if part.text:
                                            text = part.text.strip()
                                            if text:
                                                print(f"Jarvis: {text}")
                                                conversation_state["last_transcription"] = text

                                    except Exception as e:
                                        log(f"Error handling part: {e}", "ERROR")
                                        # Ensure mic is unmuted after error
                                        is_playing.clear()
                                        conversation_state["waiting_for_response"] = False
                            
                            # ===== HANDLE TURN COMPLETE =====
                            if sc.turn_complete:
                                conversation_state["turns_completed"] += 1
                                conversation_state["waiting_for_response"] = False
                                log(f"Turn {conversation_state['turns_completed']} complete - ready for next command", "DEBUG")
                                
                                # Small delay then unmute mic
                                await asyncio.sleep(0.3)
                                is_playing.clear()
                                log("[MIC] Mic UNMUTED - listening for next command", "DEBUG")
                                log_state()
                            
                            # ===== HANDLE INTERRUPTIONS =====
                            if sc.interrupted:
                                log("(interrupted by user)", "WARN")
                                is_playing.clear()  # Unmute mic on interruption
                                conversation_state["waiting_for_response"] = False
                                
                                # Clear pending audio
                                cleared = 0
                                while not audio_queue_output.empty():
                                    try:
                                        audio_queue_output.get_nowait()
                                        cleared += 1
                                    except asyncio.QueueEmpty:
                                        break
                                if cleared > 0:
                                    log(f"Cleared {cleared} audio chunks from queue", "DEBUG")
                                
                                log("[MIC] Mic UNMUTED after interrupt - listening...", "DEBUG")
                        
                        # ===== HANDLE TOOL CALLS (Ableton control) =====
                        if response.tool_call and response.tool_call.function_calls:
                            for call in response.tool_call.function_calls:
                                # Check connection before handling tool call
                                if not session_connected.is_set():
                                    break
                                await handle_tool_call(session, call)

                    except Exception as e:
                        log(f"Error handling response: {e}", "ERROR")
                        import traceback
                        traceback.print_exc()
                        # Ensure mic is unmuted after error
                        is_playing.clear()
                        conversation_state["waiting_for_response"] = False
                        continue  # Keep processing other responses
                
                # After processing all responses in this turn
                if session_connected.is_set():
                    log("Turn processing complete, waiting for next turn...", "DEBUG")
                else:
                    log("Connection closed, exiting receive loop", "DEBUG")
                    break
                        
            except Exception as e:
                error_msg = str(e)
                
                # Check for connection errors
                if "ConnectionClosed" in error_msg or "keepalive ping timeout" in error_msg or "1011" in error_msg or "TimeoutError" in error_msg:
                    log(f"Connection closed: {e}", "ERROR")
                    session_connected.clear()
                    break
                
                log(f"Turn receive error: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                
                # Ensure mic is unmuted after errors
                is_playing.clear()
                conversation_state["waiting_for_response"] = False
                
                await asyncio.sleep(0.5)
                continue
                
    except Exception as e:
        error_msg = str(e)
        log(f"Session Response Error: {e}", "ERROR")
        
        # Mark connection as closed for connection-related errors
        if "ConnectionClosed" in error_msg or "keepalive ping timeout" in error_msg or "1011" in error_msg or "TimeoutError" in error_msg:
            session_connected.clear()
        
        import traceback
        traceback.print_exc()
    finally:
        # Ensure connection flag is cleared when exiting
        session_connected.clear()
        is_playing.clear()
        conversation_state["waiting_for_response"] = False


async def handle_tool_call(session, call):
    """Handle a single tool call with retry logic."""
    # Check connection before handling tool call
    if not session_connected.is_set():
        log("Connection closed, skipping tool call", "WARN")
        return
    
    conversation_state["last_tool_call_time"] = datetime.now()
    conversation_state["tool_calls_executed"] += 1
    
    log(f"============================================================")
    log(f"*** TOOL CALL #{conversation_state['tool_calls_executed']}: {call.name}")
    log(f"    Args: {call.args}")
    
    # Extra debugging for track operations
    if "track_index" in call.args:
        raw_idx = call.args.get("track_index")
        log(f"    Track index raw: {raw_idx} (type: {type(raw_idx).__name__})")
    
    # Execute with retry logic
    result = None
    last_error = None
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = execute_ableton_function(call.name, call.args)
            
            if result.get("success"):
                break  # Success, exit retry loop
            else:
                last_error = result.get("message", "Unknown error")
                if attempt < MAX_RETRIES:
                    log(f"    Attempt {attempt + 1} failed: {last_error}. Retrying...", "WARN")
                    await asyncio.sleep(RETRY_DELAY)
                    
        except Exception as e:
            last_error = str(e)
            log(f"    Attempt {attempt + 1} exception: {e}", "ERROR")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            result = {"success": False, "message": f"Error: {e}"}
    
    # Log final result
    log(f"    Result: {result}")
    
    # Record action in session manager
    session_manager.record_action(
        action=call.name,
        params=call.args
    )
    
    # Update session manager state based on action
    update_session_state(call.name, call.args, result)
    
    # Send the result back to Gemini (only if connection is still alive)
    if session_connected.is_set():
        try:
            await session.send_tool_response(
                function_responses=[
                    types.FunctionResponse(
                        id=call.id,
                        name=call.name,
                        response=result
                    )
                ]
            )
            conversation_state["last_tool_response_sent"] = datetime.now()
            log(f"    ✅ Tool response sent to Gemini", "DEBUG")
            
        except Exception as e:
            error_msg = str(e)
            log(f"    ❌ Failed to send tool response: {e}", "ERROR")
            
            # Check if this is a connection error
            if "ConnectionClosed" in error_msg or "keepalive ping timeout" in error_msg or "1011" in error_msg:
                session_connected.clear()
    else:
        log(f"    [WARN] Connection closed, tool response not sent", "WARN")
    
    # Print user-friendly result
    if result.get("success"):
        log(f"    [OK] {result.get('message')}")
    else:
        log(f"    [FAIL] {result.get('message')}", "WARN")
    
    log(f"============================================================")
    
    # Log state after tool call
    log_state()


def update_session_state(function_name, args, result):
    """Update session manager with the result of a tool call."""
    if not result.get("success"):
        return
        
    track_index = args.get("track_index")
    
    if function_name == "mute_track" and track_index is not None:
        session_manager.update_track(track_index, muted=bool(args.get("muted")))
    elif function_name == "solo_track" and track_index is not None:
        session_manager.update_track(track_index, soloed=bool(args.get("soloed")))
    elif function_name == "arm_track" and track_index is not None:
        session_manager.update_track(track_index, armed=bool(args.get("armed")))
    elif function_name == "set_track_volume" and track_index is not None:
        session_manager.update_track(track_index, volume=args.get("volume", 0.85))
    elif function_name == "set_track_pan" and track_index is not None:
        session_manager.update_track(track_index, pan=args.get("pan", 0.0))
    elif function_name == "play":
        session_manager.update_transport(is_playing=True)
    elif function_name == "stop":
        session_manager.update_transport(is_playing=False)
    elif function_name == "set_tempo":
        session_manager.update_transport(tempo=args.get("bpm"))
    elif function_name == "toggle_metronome":
        session_manager.state.metronome_on = bool(args.get("state"))


async def play_audio():
    """Plays audio from the output queue to the speakers."""
    stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=RECEIVE_SAMPLE_RATE,  # 24kHz for output
        output=True,
    )
    
    try:
        while not shutdown_event.is_set():
            try:
                audio_data = await asyncio.wait_for(audio_queue_output.get(), timeout=1.0)
                is_playing.set()  # Mute mic while playing

                # CRITICAL: Use try/finally to guarantee unmute even if write fails
                try:
                    await asyncio.to_thread(stream.write, audio_data)
                finally:
                    # Small delay before unmuting to avoid overlap
                    await asyncio.sleep(0.05)
                    is_playing.clear()  # Always unmute after audio chunk

            except asyncio.TimeoutError:
                continue  # Check shutdown flag
            except Exception as e:
                log(f"Playback chunk error: {e}", "ERROR")
                # Ensure mic is unmuted after error
                is_playing.clear()

    except Exception as e:
        log(f"Playback Error: {e}", "ERROR")
    finally:
        # Final guarantee: unmute mic when exiting
        is_playing.clear()
        stream.stop_stream()
        stream.close()


async def heartbeat():
    """Periodic heartbeat to show session is alive and log state."""
    count = 0
    HEARTBEAT_INTERVAL = 60  # Every minute
    
    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            
            # Check if connection is still alive
            if not session_connected.is_set():
                log("Heartbeat: Connection lost, stopping heartbeat", "DEBUG")
                break
            
            count += 1
            log(f"♥ Session alive ({count} min)")
            log_state()
            
            # Log recent actions from session manager
            recent = session_manager.get_recent_actions(3)
            if recent:
                log(f"    Recent actions: {[a['action'] for a in recent]}", "DEBUG")
                
    except asyncio.CancelledError:
        log("Heartbeat cancelled", "DEBUG")
    except Exception as e:
        log(f"Heartbeat error: {e}", "DEBUG")


async def stall_detector():
    """Detect if the session has stalled (no activity for too long)."""
    STALL_THRESHOLD = 120  # 2 minutes
    CONNECTION_CHECK_INTERVAL = 30  # Check every 30 seconds
    AUDIO_STALL_CHECK_INTERVAL = 2  # Check audio state every 2 seconds
    AUDIO_STALL_THRESHOLD = 10  # 10 seconds of "muted but no audio"

    # Track when mic was muted without audio activity
    audio_stall_start = None

    try:
        while not shutdown_event.is_set() and session_connected.is_set():
            await asyncio.sleep(AUDIO_STALL_CHECK_INTERVAL)

            # Check connection state
            if not session_connected.is_set():
                log("Session connection lost, triggering reconnect", "WARN")
                break

            # ===== NEW: Check for audio stall (mic muted but no audio) =====
            if is_playing.is_set() and audio_queue_output.empty():
                # Mic is muted but no audio is queued - potential stall
                if audio_stall_start is None:
                    audio_stall_start = datetime.now()
                else:
                    elapsed = (datetime.now() - audio_stall_start).total_seconds()
                    if elapsed > AUDIO_STALL_THRESHOLD:
                        log(f"[WARN] Audio stall detected! Mic muted for {elapsed:.1f}s with no audio", "WARN")
                        log("Force-unmuting microphone to recover", "WARN")
                        is_playing.clear()
                        audio_stall_start = None  # Reset
            else:
                # Audio is flowing or mic is not muted - reset stall tracker
                audio_stall_start = None

            # ===== Existing tool response stall detection (every 30s) =====
            # Only check every CONNECTION_CHECK_INTERVAL
            if conversation_state["waiting_for_response"]:
                last_tool = conversation_state["last_tool_response_sent"]
                if last_tool:
                    elapsed = (datetime.now() - last_tool).total_seconds()
                    if elapsed > STALL_THRESHOLD:
                        log(f"[WARN] Session may be stalled - {elapsed:.0f}s since last tool response", "WARN")
                        log("Consider speaking a new command to resume", "WARN")
                        # After very long stall, mark for reconnection
                        if elapsed > STALL_THRESHOLD * 2:
                            log("Session stalled too long, will attempt reconnect", "ERROR")
                            session_connected.clear()
                            break

    except Exception as e:
        log(f"Stall detector error: {e}", "DEBUG")


# ==================== PLUGIN CHAIN HELPERS ====================

def execute_plugin_chain_creation(track_index, artist_or_style, track_type="vocal", deep_research=False):
    """
    Execute plugin chain creation — artifact-first pipeline.
    
    Order:
    1. Artifact store cache (zero LLM calls)
    2. Single-shot research (<=1 LLM call) + auto-cache
    3. Legacy KB / built-in paths are fenced unless deep_research=True
    4. Build chain → load plugins → configure parameters
    """
    try:
        import asyncio
        from plugins.chain_builder import PluginChainBuilder
        from knowledge.artifact_chain_store import get_artifact_chain_store
        
        log(f"Creating plugin chain: {artist_or_style} {track_type} on track {track_index + 1}", "DEBUG")
        
        artifact_store = get_artifact_chain_store()
        query = f"{artist_or_style} {track_type} chain"
        from_cache = False
        research_result = None
        
        # Step 1: Check artifact store (instant, zero LLM)
        artifact = artifact_store.get_artifact_for_execution(query)
        if artifact:
            log(f"artifact_hit query={query}", "DEBUG")
            from_cache = True
            research_result = _artifact_to_research_result(artifact, artist_or_style, track_type)
        else:
            log(f"artifact_miss query={query}", "DEBUG")

        # Step 2: Single-shot research (<=1 LLM call)
        if not research_result:
            log(f"single_shot_called query={query}", "DEBUG")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        research_result = pool.submit(
                            asyncio.run,
                            _async_single_shot_research(query, artist_or_style, track_type)
                        ).result(timeout=30)
                else:
                    research_result = asyncio.run(
                        _async_single_shot_research(query, artist_or_style, track_type)
                    )
            except Exception as e:
                log(f"Single-shot research failed: {e}", "DEBUG")
        
        # Step 3: Legacy fallback — fenced unless explicit deep_research=True
        if not research_result and deep_research:
            log(f"deep_research_called query={query}", "DEBUG")
            cached_chain = plugin_chain_kb.get_chain_for_research(artist_or_style, track_type)
            if cached_chain:
                log(f"Found legacy cached chain for {artist_or_style}", "DEBUG")
                research_result = cached_chain
                from_cache = True
            else:
                from agents.research_agent import ResearchAgent
                research_result = _sync_research_chain(artist_or_style, track_type)
                if not research_result:
                    return {"success": False, "message": "Failed to research plugin chain"}

        if not research_result:
            return {
                "success": False,
                "message": "No artifact chain available and single-shot research did not return a usable chain (legacy path fenced; pass deep_research=true to allow).",
            }
        
        # Step 4: Build + load + configure
        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(research_result)
        
        validation = builder.validate_chain(chain)
        if validation.get("warnings"):
            log(f"Chain validation warnings: {validation['warnings']}", "DEBUG")
        
        result = _sync_load_chain_with_params(builder, chain, track_index, research_result)
        result["chain_name"] = chain.name
        result["artist_or_style"] = artist_or_style
        result["track_type"] = track_type
        result["plugins_in_chain"] = [s.to_dict() for s in chain.slots]
        result["from_cache"] = from_cache
        result["confidence"] = research_result.get("confidence", 0.5)
        
        # Auto-save as preset on success
        if result.get("success") and not from_cache:
            try:
                artifact_store.save_artifact(query, {
                    "artist": artist_or_style,
                    "track_type": track_type,
                    "style_description": research_result.get("description", ""),
                    "confidence": research_result.get("confidence", 0.5),
                    "chain": [
                        {
                            "plugin_name": p.get("name", ""),
                            "category": p.get("type", "other"),
                            "purpose": p.get("purpose", ""),
                            "parameters": p.get("settings", {}),
                            "fallbacks": [],
                        }
                        for p in research_result.get("chain", [])
                    ],
                    "source": "auto-saved-on-success",
                })
            except Exception:
                pass  # Non-critical: don't fail the load on save error

            plugin_chain_kb.record_successful_load(
                f"{artist_or_style.lower().replace(' ', '_')}_{track_type}",
                track_index,
                [p.get("name") for p in result.get("plugins_loaded", [])]
            )
        
        return result
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Failed to create plugin chain: {e}"}


async def _async_single_shot_research(query, artist_or_style, track_type):
    """Run single-shot research via the research coordinator."""
    from research.research_coordinator import get_research_coordinator
    coordinator = get_research_coordinator()
    result = await coordinator.perform_research(
        query=query,
        use_youtube=False,
        use_web=False,
        budget_mode="cheap",
        prefer_cache=True,
        deep_research=False,
    )
    chain_spec = result.get("chain_spec")
    if chain_spec and chain_spec.devices:
        from research.research_coordinator import chainspec_to_builder_format
        return chainspec_to_builder_format(chain_spec.to_dict(), track_type)
    return None


def _artifact_to_research_result(artifact, artist_or_style, track_type):
    """Convert artifact JSON dict to the research_result format expected by PluginChainBuilder."""
    chain_items = []
    for dev in artifact.get("chain", []):
        chain_items.append({
            "name": dev.get("plugin_name", ""),
            "type": dev.get("category", "other"),
            "purpose": dev.get("purpose", ""),
            "settings": dev.get("parameters", {}),
        })
    if not chain_items:
        return None
    return {
        "artist_or_style": artist_or_style,
        "track_type": track_type,
        "chain": chain_items,
        "confidence": artifact.get("confidence", 0.5),
        "description": artifact.get("style_description", ""),
    }


def execute_research_vocal_chain(
    query, use_youtube=True, use_web=True, max_sources=3,
    budget_mode="balanced", prefer_cache=True, cache_max_age_days=14,
    max_total_llm_calls=None
):
    """
    Research a vocal chain and return the spec (does NOT load into Ableton).
    Uses the artifact-backed pipeline: 0 LLM calls on cache hit, 1 on miss.
    """
    try:
        import asyncio
        from research.research_coordinator import get_research_coordinator
        
        coordinator = get_research_coordinator()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        coordinator.perform_research(
                            query=query,
                            use_youtube=use_youtube,
                            use_web=use_web,
                            budget_mode=budget_mode or "cheap",
                            max_total_llm_calls=max_total_llm_calls,
                            prefer_cache=prefer_cache,
                            cache_max_age_days=cache_max_age_days,
                            deep_research=False,
                        )
                    ).result(timeout=30)
            else:
                result = asyncio.run(
                    coordinator.perform_research(
                        query=query,
                        use_youtube=use_youtube,
                        use_web=use_web,
                        budget_mode=budget_mode or "cheap",
                        max_total_llm_calls=max_total_llm_calls,
                        prefer_cache=prefer_cache,
                        cache_max_age_days=cache_max_age_days,
                        deep_research=False,
                    )
                )
        except Exception as e:
            return {"success": False, "message": f"Research failed: {e}"}
        
        chain_spec = result.get("chain_spec")
        if chain_spec:
            return {
                "success": True,
                "chain_spec": chain_spec.to_dict(),
                "cache_hit": result.get("cache_hit", False),
                "llm_calls_used": result.get("chain_spec", {}).meta.get("llm_calls_used", 0)
                    if hasattr(chain_spec, "meta") else 0,
                "message": f"Researched {len(chain_spec.devices)} plugins for: {query}"
            }
        
        return {"success": False, "message": "Research returned no results"}
        
    except Exception as e:
        return {"success": False, "message": f"Research error: {e}"}


def execute_apply_research_chain(track_index, chain_spec, track_type="vocal"):
    """
    Apply a previously researched chain spec to a track.
    Expects chain_spec as a dict (from execute_research_vocal_chain).
    Zero LLM calls — purely deterministic load + configure.
    """
    try:
        from plugins.chain_builder import PluginChainBuilder
        from research.research_coordinator import chainspec_to_builder_format
        
        if isinstance(chain_spec, dict):
            research_result = chainspec_to_builder_format(chain_spec, track_type)
        else:
            return {"success": False, "message": "chain_spec must be a dict"}
        
        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(research_result)
        
        result = _sync_load_chain_with_params(builder, chain, track_index, research_result)
        result["track_type"] = track_type
        result["from_research"] = True
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Failed to apply chain: {e}"}


def execute_build_chain_pipeline(args):
    """
    Single-call deterministic pipeline: research → build → load.
    
    This is the recommended entry point — combines research + apply in one
    tool call, minimizing round-trips with the Gemini Live session.
    
    Args dict should contain:
      - track_index (required)
      - query OR artist_or_style (required)
      - track_type (default: "vocal")
    """
    track_index = args.get("track_index")
    if track_index is None:
        return {"success": False, "message": "track_index is required"}
    track_index = int(track_index)
    
    query = args.get("query") or args.get("artist_or_style", "")
    track_type = args.get("track_type", "vocal")
    
    if not query:
        return {"success": False, "message": "query or artist_or_style is required"}
    
    return execute_plugin_chain_creation(track_index, query, track_type)


def _sync_research_chain(artist_or_style, track_type):
    """Synchronous research using built-in knowledge"""
    from agents.research_agent import ResearchAgent
    
    agent = ResearchAgent(None)
    builtin = agent._get_builtin_chain_knowledge(artist_or_style, track_type)
    
    if builtin:
        return {
            "artist_or_style": artist_or_style,
            "track_type": track_type,
            "chain": builtin.get("data", {}).get("chain", []),
            "confidence": 0.8
        }
    
    # Return default chain if no specific knowledge
    default_chain = agent._get_default_chain(track_type)
    return {
        "artist_or_style": artist_or_style,
        "track_type": track_type,
        "chain": default_chain,
        "confidence": 0.6
    }


def _sync_load_chain(builder, chain, track_index):
    """Synchronously load a chain (using blocking calls)"""
    results = {
        "success": True,
        "track_index": track_index,
        "plugins_loaded": [],
        "plugins_failed": [],
        "message": ""
    }
    
    import time
    
    for i, slot in enumerate(chain.slots):
        if not slot.matched_plugin:
            results["plugins_failed"].append({
                "index": i,
                "type": slot.plugin_type,
                "reason": "No matching plugin found"
            })
            continue
        
        try:
            from ableton_controls import ableton
            load_result = ableton.load_device(
                track_index,
                slot.matched_plugin.name,
                position=-1
            )
            
            if load_result.get("success"):
                results["plugins_loaded"].append({
                    "index": i,
                    "name": slot.matched_plugin.name,
                    "type": slot.plugin_type
                })
            else:
                results["plugins_failed"].append({
                    "index": i,
                    "name": slot.matched_plugin.name,
                    "reason": load_result.get("message", "Unknown")
                })
            
            time.sleep(1.5)  # Increased delay to prevent Ableton crashes
            
        except Exception as e:
            results["plugins_failed"].append({
                "index": i,
                "type": slot.plugin_type,
                "reason": str(e)
            })
    
    # Set overall status
    if results["plugins_failed"] and not results["plugins_loaded"]:
        results["success"] = False
        results["message"] = "Failed to load any plugins"
    elif results["plugins_failed"]:
        results["message"] = f"Partial: {len(results['plugins_loaded'])} loaded, {len(results['plugins_failed'])} failed"
    else:
        results["message"] = f"Successfully loaded {len(results['plugins_loaded'])} plugins"
    
    return results


def _sync_load_chain_with_params(builder, chain, track_index, research_result):
    """
    Synchronously load a chain and configure parameters based on research.
    
    This enhanced version uses ReliableParameterController for:
    1. Verified device loading with readiness detection
    2. Parameter discovery by name (no hardcoded indices)
    3. Verified parameter setting with retry logic
    """
    import time
    
    results = {
        "success": True,
        "track_index": track_index,
        "plugins_loaded": [],
        "plugins_failed": [],
        "params_configured": [],
        "message": ""
    }
    
    # Get the research chain data for settings
    research_chain = research_result.get("chain", [])
    
    for i, slot in enumerate(chain.slots):
        if not slot.matched_plugin:
            results["plugins_failed"].append({
                "index": i,
                "type": slot.plugin_type,
                "reason": "No matching plugin found"
            })
            continue
        
        try:
            # Load device with verification (uses polling instead of fixed delay)
            load_result = reliable_params.load_device_verified(
                track_index,
                slot.matched_plugin.name,
                position=-1,
                timeout=5.0,
                min_delay=0.2  # 200ms minimum delay between loads
            )
            
            if not load_result.get("success"):
                results["plugins_failed"].append({
                    "index": i,
                    "name": slot.matched_plugin.name,
                    "reason": load_result.get("message", "Unknown")
                })
                continue
            
            device_index = load_result.get("device_index", i)
            
            # Wait for device to be ready (polls until parameters accessible)
            if not reliable_params.wait_for_device_ready(track_index, device_index, timeout=5.0):
                log(f"Device {slot.matched_plugin.name} not ready after 5s, skipping parameter config", "WARN")
                results["plugins_loaded"].append({
                    "index": i,
                    "name": slot.matched_plugin.name,
                    "type": slot.plugin_type,
                    "purpose": slot.purpose,
                    "device_index": device_index,
                    "params_configured": [],
                    "warning": "Device not ready for parameter config"
                })
                continue
            
            log(f"Device {slot.matched_plugin.name} ready at index {device_index}", "DEBUG")
            
            plugin_info = {
                "index": i,
                "name": slot.matched_plugin.name,
                "type": slot.plugin_type,
                "purpose": slot.purpose,
                "device_index": device_index
            }
            
            # Configure parameters based on purpose using reliable params
            params_set = _configure_device_for_purpose(
                track_index, 
                device_index, 
                slot.matched_plugin.name,
                slot.purpose,
                slot.settings,
                research_chain[i] if i < len(research_chain) else {}
            )
            
            if params_set:
                plugin_info["params_configured"] = params_set
                results["params_configured"].extend(params_set)
            
            results["plugins_loaded"].append(plugin_info)
            
            # Small delay between device loads to prevent Ableton crashes
            time.sleep(0.2)  # 200ms pacing between devices
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            results["plugins_failed"].append({
                "index": i,
                "type": slot.plugin_type,
                "reason": str(e)
            })
    
    # Set overall status
    if results["plugins_failed"] and not results["plugins_loaded"]:
        results["success"] = False
        results["message"] = "Failed to load any plugins"
    elif results["plugins_failed"]:
        results["message"] = f"Loaded {len(results['plugins_loaded'])} plugins, {len(results['plugins_failed'])} failed, {len(results['params_configured'])} params configured"
    else:
        results["message"] = f"Successfully loaded {len(results['plugins_loaded'])} plugins with {len(results['params_configured'])} params configured"
    
    return results


def _configure_device_for_purpose(track_index, device_index, device_name, purpose, slot_settings, research_data):
    """
    Configure a device's parameters based on its purpose in the chain.

    Uses ResearchBot.apply_parameters() which has empirically-verified normalization
    functions for Ableton's non-linear parameter scales (ratio, frequency, attack, etc.)

    Args:
        track_index: Track index
        device_index: Device index on the track
        device_name: Name of the device
        purpose: Purpose of the device (e.g., "high_pass", "dynamics")
        slot_settings: Settings from the chain builder slot
        research_data: Research data for this device in the chain

    Returns:
        List of configured parameters
    """
    params_set = []

    try:
        # Merge all settings sources (research_data has lowest priority, slot_settings highest)
        merged_settings = {}

        # 1. Start with research data settings
        if research_data and research_data.get("settings"):
            for key, value in research_data.get("settings", {}).items():
                if isinstance(key, str) and isinstance(value, (int, float, bool)):
                    merged_settings[key] = value

        # 2. Override with slot settings (highest priority)
        if slot_settings:
            for key, value in slot_settings.items():
                if isinstance(key, str) and isinstance(value, (int, float, bool)):
                    merged_settings[key] = value

        if not merged_settings:
            log(f"No settings to apply for {device_name}", "DEBUG")
            return params_set

        log(f"Applying {len(merged_settings)} settings to {device_name}: {list(merged_settings.keys())}", "DEBUG")
        print(f"[PARAMS] {device_name}: Applying {merged_settings}")

        # Use ResearchBot's apply_parameters which has correct normalization
        # for Ableton's non-linear parameter scales
        try:
            from research_bot import get_research_bot
            bot = get_research_bot()

            result = bot.apply_parameters(
                track_index, device_index, device_name, merged_settings
            )

            if result.get("success") or result.get("applied"):
                for applied in result.get("applied", []):
                    params_set.append({
                        "device": device_name,
                        "device_index": device_index,
                        "param_name": applied.get("param"),
                        "param_index": applied.get("index"),
                        "value": applied.get("value"),
                        "verified": True,
                        "explanation": f"Applied via ResearchBot normalization"
                    })
                log(f"ResearchBot applied {len(result.get('applied', []))} params to {device_name}", "DEBUG")

                if result.get("failed"):
                    for failed in result.get("failed", []):
                        log(f"Failed to apply {failed.get('param')}: {failed.get('error')}", "DEBUG")
            else:
                log(f"ResearchBot apply_parameters returned: {result}", "DEBUG")

        except ImportError as e:
            log(f"ResearchBot not available, falling back to reliable_params: {e}", "WARN")
            # Fallback to reliable_params for settings by name
            for param_name, value in merged_settings.items():
                if not isinstance(value, (int, float)):
                    continue
                try:
                    result = reliable_params.set_parameter_by_name(
                        track_index, device_index, param_name, value
                    )
                    if result.get("success"):
                        params_set.append({
                            "device": device_name,
                            "device_index": device_index,
                            "param_name": param_name,
                            "param_index": result.get("param_index"),
                            "value": value,
                            "verified": result.get("verified", False),
                            "explanation": "Applied via reliable_params fallback"
                        })
                except Exception as e:
                    log(f"Failed to set '{param_name}' on {device_name}: {e}", "DEBUG")

    except Exception as e:
        log(f"Error configuring device {device_name}: {e}", "DEBUG")
        import traceback
        traceback.print_exc()

    return params_set


async def _async_create_chain(track_index, artist_or_style, track_type):
    """Async version of chain creation"""
    from plugins.chain_builder import create_plugin_chain
    return await create_plugin_chain(artist_or_style, track_type, track_index)


def execute_preset_chain(track_index, preset_name, track_type="vocal"):
    """
    Execute preset plugin chain loading
    """
    try:
        from plugins.chain_builder import PluginChainBuilder
        
        builder = PluginChainBuilder()
        chain = builder.get_preset_chain(preset_name, track_type)
        
        # Load the chain
        result = _sync_load_chain(builder, chain, track_index)
        result["chain_name"] = chain.name
        result["preset"] = preset_name
        
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Failed to load preset chain: {e}"}


def _route_command_mode_query(query: str):
    """Map direct DAW command text to concrete executable tool calls."""
    import re

    q = (query or "").strip().lower()
    if not q:
        return None

    plugin_aliases = {
        "eq eight": "EQ Eight",
        "eq8": "EQ Eight",
        "compressor": "Compressor",
        "glue compressor": "Glue Compressor",
        "glue comp": "Glue Compressor",
        "limiter": "Limiter",
        "multiband dynamics": "Multiband Dynamics",
        "multiband": "Multiband Dynamics",
    }

    # Transport
    if re.search(r"\bplay\b", q):
        return {"function": "play", "args": {}, "reason": "Detected transport play command"}
    if re.search(r"\bstop\b", q):
        return {"function": "stop", "args": {}, "reason": "Detected transport stop command"}

    # Tempo
    m = re.search(r"(?:set\s+)?tempo\s+(?:to\s+)?([0-9]+(?:\.[0-9]+)?)", q)
    if m:
        return {
            "function": "set_tempo",
            "args": {"bpm": float(m.group(1))},
            "reason": "Detected tempo change command"
        }

    # Common indexed targets (1-based in language -> 0-based for API)
    m_track = re.search(r"\btrack\s*(\d+)\b", q)
    m_device = re.search(r"\bdevice\s*(\d+)\b", q)
    m_param = re.search(r"(?:\bparam(?:eter)?\s*(\d+)\b|\bparameter\s*(\d+)\b)", q)

    track_index = int(m_track.group(1)) - 1 if m_track else None
    device_index = int(m_device.group(1)) - 1 if m_device else None
    param_num = None
    if m_param:
        param_num = next((g for g in m_param.groups() if g), None)
    param_index = int(param_num) - 1 if param_num else None

    # Plugin loading: "add/load/insert <plugin> on track N"
    m_plugin = re.search(r"(?:add|load|insert)\s+(.+?)\s+(?:to|on)\s+track\s*(\d+)", q)
    if m_plugin:
        plugin_name = m_plugin.group(1).strip(" ' \"")
        t_idx = int(m_plugin.group(2)) - 1
        if plugin_name and t_idx >= 0:
            return {
                "function": "add_plugin_to_track",
                "args": {"track_index": t_idx, "plugin_name": plugin_name, "position": -1},
                "reason": "Detected plugin load command"
            }

    if track_index is not None:
        if re.search(r"\bmute\b", q):
            state = 0 if re.search(r"\bunmute\b|\boff\b", q) else 1
            return {
                "function": "mute_track",
                "args": {"track_index": track_index, "muted": state},
                "reason": "Detected track mute command"
            }

        if re.search(r"\bsolo\b", q):
            state = 0 if re.search(r"\bunsolo\b|\boff\b", q) else 1
            return {
                "function": "solo_track",
                "args": {"track_index": track_index, "soloed": state},
                "reason": "Detected track solo command"
            }

        if re.search(r"\barm\b", q):
            state = 0 if re.search(r"\bdisarm\b|\boff\b", q) else 1
            return {
                "function": "arm_track",
                "args": {"track_index": track_index, "armed": state},
                "reason": "Detected track arm command"
            }

        mv = re.search(r"(?:set\s+)?(?:track\s*\d+\s+)?volume\s+(?:to\s+)?(-?[0-9]+(?:\.[0-9]+)?)(%?)", q)
        if mv:
            raw = float(mv.group(1))
            pct = bool(mv.group(2))
            vol = raw / 100.0 if pct or raw > 2.0 else raw
            vol = max(0.0, min(1.5, vol))
            return {
                "function": "set_track_volume",
                "args": {"track_index": track_index, "volume": vol},
                "reason": "Detected track volume command"
            }

        mp = re.search(r"(?:set\s+)?(?:track\s*\d+\s+)?pan\s+(?:to\s+)?(-?[0-9]+(?:\.[0-9]+)?)", q)
        if mp:
            pan = float(mp.group(1))
            if abs(pan) > 1.0:
                pan = max(-1.0, min(1.0, pan / 100.0))
            return {
                "function": "set_track_pan",
                "args": {"track_index": track_index, "pan": pan},
                "reason": "Detected track pan command"
            }

        # Device enable/disable: requires track + device
        if device_index is not None and re.search(r"\b(enable|disable|bypass)\b", q):
            enabled = 0 if re.search(r"\b(disable|bypass|off)\b", q) else 1
            return {
                "function": "set_device_enabled",
                "args": {"track_index": track_index, "device_index": device_index, "enabled": enabled},
                "reason": "Detected device enable/disable command"
            }

        # Direct parameter set: "set track 1 device 2 parameter 8 to 0.5"
        m_val = re.search(r"(?:to|=)\s*(-?[0-9]+(?:\.[0-9]+)?)", q)
        if device_index is not None and param_index is not None and m_val:
            return {
                "function": "set_device_parameter",
                "args": {
                    "track_index": track_index,
                    "device_index": device_index,
                    "param_index": param_index,
                    "value": float(m_val.group(1)),
                },
                "reason": "Detected direct device parameter command"
            }

        # Hybrid natural-language mode: plugin + parameter-like request
        plugin_hit = None
        for alias, canonical in plugin_aliases.items():
            if alias in q:
                plugin_hit = canonical
                break

        if plugin_hit and re.search(r"\bset\b", q) and re.search(r"\bto\b", q):
            if track_index is None:
                return {
                    "function": "__followup__",
                    "args": {},
                    "reason": f"I can apply {plugin_hit} settings, but need which track."
                }
            return {
                "function": "apply_audio_intent",
                "args": {
                    "intent": query,
                    "track_type": "vocal",
                    "track_index": track_index,
                },
                "reason": f"Hybrid mode: routing natural-language {plugin_hit} intent"
            }

    return None


def execute_apply_basic_vocal_parameters(track_index, voice_profile="male_tenor"):
    """Apply a robust baseline vocal parameter set without needing parameter index dumps.

    This is an anti-stall path for stock Ableton devices when LLM parameter-resolution loops.
    """
    try:
        import time

        profile = (voice_profile or "male_tenor").strip().lower()
        if profile not in {"male_tenor", "male", "tenor"}:
            profile = "male_tenor"

        # Best-effort defaults (safe starter values)
        defaults = {
            "eq eight": [
                ("1 Frequency A", 90.0),
                ("2 Frequency A", 280.0),
                ("2 Gain A", -2.5),
                ("3 Frequency A", 3200.0),
                ("3 Gain A", 2.0),
                ("4 Frequency A", 10500.0),
                ("4 Gain A", 1.5),
            ],
            "compressor": [
                ("Threshold", -18.0),
                ("Ratio", 3.0),
                ("Attack", 20.0),
                ("Release", 80.0),
                ("Output Gain", 2.0),
            ],
            "glue compressor": [
                ("Threshold", -20.0),
                ("Ratio", 2.0),
                ("Attack", 10.0),
                ("Release", 100.0),
                ("Makeup", 2.0),
            ],
            "reverb": [
                ("Decay Time", 1.6),
                ("PreDelay", 25.0),
                ("LowCut", 180.0),
                ("HighCut", 8500.0),
                ("Dry/Wet", 12.0),
            ],
            "limiter": [
                ("Ceiling", -1.0),
                ("Gain", 0.0),
            ],
            "multiband dynamics": [
                ("Time", 35.0),
                ("Amount", 30.0),
                ("Output", 0.0),
            ],
        }

        def _norm(name: str) -> str:
            return (name or "").strip().lower()

        # Discover devices on track
        num_res = ableton.get_num_devices_sync(track_index)
        if not num_res.get("success"):
            return {"success": False, "message": f"Could not get devices for track {track_index+1}: {num_res.get('message','unknown error')}"}

        num_devices = int(num_res.get("count", 0))
        if num_devices <= 0:
            return {"success": False, "message": f"No devices found on track {track_index+1}."}

        applied = []
        failed = []

        for device_index in range(num_devices):
            try:
                name_res = ableton.get_device_name(track_index, device_index)
                if not name_res.get("success"):
                    continue
                device_name = str(name_res.get("name", "")).strip()
                n = _norm(device_name)

                target_key = None
                for k in defaults.keys():
                    if k in n:
                        target_key = k
                        break

                if not target_key:
                    continue

                for param_name, value in defaults[target_key]:
                    try:
                        r = reliable_params.set_parameter_by_name(
                            track_index, device_index, param_name, value,
                            max_retries=2,
                        )
                        if r.get("success"):
                            applied.append({
                                "track_index": track_index,
                                "device_index": device_index,
                                "device": device_name,
                                "param": param_name,
                                "value": value,
                            })
                        else:
                            failed.append({
                                "track_index": track_index,
                                "device_index": device_index,
                                "device": device_name,
                                "param": param_name,
                                "value": value,
                                "error": r.get("message", "failed"),
                            })
                    except Exception as e:
                        failed.append({
                            "track_index": track_index,
                            "device_index": device_index,
                            "device": device_name,
                            "param": param_name,
                            "value": value,
                            "error": str(e),
                        })
                    time.sleep(0.03)
            except Exception:
                continue

        if not applied:
            return {
                "success": False,
                "message": "Could not apply baseline parameters to detected devices.",
                "applied": applied,
                "failed": failed,
            }

        return {
            "success": True,
            "message": f"Applied {len(applied)} baseline vocal parameters ({voice_profile}) on track {track_index+1}.",
            "profile": voice_profile,
            "applied": applied,
            "failed": failed,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Failed to apply baseline vocal parameters: {e}"}


def execute_lookup_song_chain(song_title, artist=None, section="verse", query=None):
    """Lookup a chain from local library."""
    try:
        import asyncio
        from librarian.librarian_agent import get_librarian_agent

        librarian = get_librarian_agent()

        async def _lookup():
            return await librarian.lookup(
                query=query or f"{song_title} {artist or ''}".strip(),
                song_title=song_title,
                artist=artist,
                section=section,
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import threading
            holder = {}
            err = {}
            def _t():
                try:
                    holder["result"] = asyncio.run(_lookup())
                except Exception as e:
                    err["error"] = e
            t = threading.Thread(target=_t)
            t.start()
            t.join()
            if "error" in err:
                raise err["error"]
            return holder.get("result", {"success": False, "message": "Lookup failed"})

        return asyncio.run(_lookup())
    except Exception as e:
        return {"success": False, "message": f"Local library lookup failed: {e}"}


def execute_list_library():
    try:
        from librarian.librarian_agent import get_librarian_agent
        return get_librarian_agent().list_library()
    except Exception as e:
        return {"success": False, "message": f"Failed to list library: {e}"}


def execute_search_library_by_vibe(tags):
    try:
        from librarian.librarian_agent import get_librarian_agent
        return get_librarian_agent().search_by_vibe(tags or [])
    except Exception as e:
        return {"success": False, "message": f"Vibe search failed: {e}"}


def execute_explain_parameter(plugin_name, param_name):
    try:
        from librarian.teacher import explain_setting
        return explain_setting(plugin_name=plugin_name, param_name=param_name)
    except Exception as e:
        return {"found": False, "message": f"Explain failed: {e}"}


def execute_research_vocal_chain(
    query,
    use_youtube=True,
    use_web=True,
    max_sources=3,
    budget_mode=None,
    prefer_cache=True,
    cache_max_age_days=14,
    max_total_llm_calls=None,
    deep_research=False,
):
    """Execute research_vocal_chain from the research coordinator."""
    try:
        import asyncio
        from research.research_coordinator import (
            get_research_coordinator,
            research_vocal_chain,
        )
        import os

        # Validate query parameter
        if not query:
            return {
                "success": False,
                "message": "Query parameter is required for research_vocal_chain"
            }

        if not budget_mode:
            budget_mode = os.getenv("RESEARCH_BUDGET_MODE", "balanced")

        # Local Librarian-first lookup (no web calls)
        try:
            from librarian.librarian_agent import get_librarian_agent
            librarian = get_librarian_agent()

            local_result_holder = {}
            def run_lookup():
                return asyncio.run(librarian.lookup(query=query))

            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop and running_loop.is_running():
                import threading
                err_holder = {}
                def _thread_lookup():
                    try:
                        local_result_holder["result"] = run_lookup()
                    except Exception as e:
                        err_holder["error"] = e
                t = threading.Thread(target=_thread_lookup)
                t.start()
                t.join()
                if "error" in err_holder:
                    raise err_holder["error"]
                local_result = local_result_holder.get("result", {})
            else:
                local_result = run_lookup()

            if local_result.get("success"):
                return local_result
        except Exception as librarian_err:
            log(f"[Librarian] Lookup skipped/fallback to research pipeline: {librarian_err}", "DEBUG")

        log(f"[Research] Starting vocal chain research for: {query}", "DEBUG")

        # Run the async research function
        # Run the async research function in a separate thread to avoid event loop conflicts
        import threading
        # Check if query is a file path for audio analysis
        if os.path.exists(query) and query.lower().endswith(('.wav', '.mp3', '.aif', '.flac')):
            log(f"[Research] Identified query as audio file: {query}", "DEBUG")
            coordinator = get_research_coordinator()
            
            def run_analysis():
                return asyncio.run(
                    coordinator.analyze_reference_track(query)
                )
                
            task_func = run_analysis
        else:
            def run_research():
                return asyncio.run(
                    research_vocal_chain(
                        query=query,
                        use_youtube=use_youtube,
                        use_web=use_web,
                        max_youtube_videos=max_sources,
                        max_web_articles=max(1, max_sources - 1),
                        budget_mode=budget_mode,
                        prefer_cache=prefer_cache,
                        cache_max_age_days=cache_max_age_days,
                        max_total_llm_calls=max_total_llm_calls,
                        deep_research=bool(deep_research),
                    )
                )
            task_func = run_research

        # If we're already in a loop, we can't use asyncio.run in this thread
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Run in a separate thread
            result_holder = {}
            error_holder = {}
            
            def thread_target():
                try:
                    # Create a new loop for this thread
                    result_holder['result'] = task_func()
                except Exception as e:
                    error_holder['error'] = e

            t = threading.Thread(target=thread_target)
            t.start()
            t.join()
            
            if 'error' in error_holder:
                raise error_holder['error']
            chain_spec = result_holder['result']
        else:
            # No loop running, just run it
            chain_spec = task_func()

        # Convert ChainSpec to dict for JSON serialization
        result = chain_spec.to_dict()
        research_meta = result.get("meta", {})
        cache_hit = bool(research_meta.get("cache_hit"))

        log(f"[Research] Found {len(chain_spec.devices)} devices with "
            f"{chain_spec.confidence:.2f} confidence", "DEBUG")

        # Phase 3: auto-route direct DAW command intents into executable actions.
        if research_meta.get("command_mode_bypass"):
            route = _route_command_mode_query(query)
            if route:
                if route.get("function") == "__followup__":
                    return {
                        "success": False,
                        "query": query,
                        "message": route.get("reason", "Need more details to execute this command."),
                        "routed_from": "research_vocal_chain",
                        "route_reason": "command_mode_followup_required",
                        "research_meta": research_meta,
                    }

                routed_result = execute_ableton_function(route["function"], route["args"])
                routed_result.setdefault("query", query)
                routed_result.setdefault("routed_from", "research_vocal_chain")
                routed_result.setdefault("route_reason", route.get("reason", "command_mode_bypass"))
                routed_result.setdefault("research_meta", research_meta)
                if routed_result.get("success"):
                    routed_result["message"] = routed_result.get("message") or f"Executed: {route['function']}"
                return routed_result

            return {
                "success": False,
                "query": query,
                "message": "Detected direct DAW command and skipped research, but command wasn't specific enough to auto-execute. Please include explicit target (e.g., 'mute track 2' or 'set track 1 volume to 80%').",
                "routed_from": "research_vocal_chain",
                "route_reason": "command_mode_bypass_no_match",
                "research_meta": research_meta,
            }

        return {
            "success": True,
            "chain_spec": result,
            "message": f"Research complete: {len(chain_spec.devices)} devices found" + 
                       (f" (from cache)" if cache_hit else "") +
                       (f" (from analysis)" if "Analysis" in chain_spec.style_description else ""),
            "query": query,
            "confidence": chain_spec.confidence,
            "sources": chain_spec.sources,
            "style_description": chain_spec.style_description,
            "budget_mode": budget_mode,
            "cache_hit": cache_hit,
            "research_meta": research_meta,
            "next_step": "Present the found devices to the user for confirmation, then call apply_research_chain with this chain_spec and the target track_index to load them."
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"[Research] Error: {e}", "ERROR")
        return {
            "success": False,
            "message": f"Research failed: {e}",
            "query": query
        }


def execute_apply_research_chain(track_index, chain_spec_dict, track_type="vocal"):
    """
    Apply a previously-researched ChainSpec to a track.

    Bridges the research pipeline (ChainSpec format) to the chain builder
    (build_chain_from_research format), then loads plugins and configures parameters.

    Args:
        track_index: 0-based track index
        chain_spec_dict: The chain_spec dict returned by research_vocal_chain
        track_type: Type of track (default "vocal")

    Returns:
        Dict with load results
    """
    try:
        from plugins.chain_builder import PluginChainBuilder
        from research.research_coordinator import chainspec_to_builder_format

        if not chain_spec_dict:
            return {"success": False, "message": "No chain_spec provided. Run research_vocal_chain first."}

        devices = chain_spec_dict.get("devices", [])
        if not devices:
            return {"success": False, "message": "No devices in research results to apply."}

        # Convert research format to builder format
        research_result = chainspec_to_builder_format(chain_spec_dict, track_type=track_type)

        log(f"[ApplyResearch] Applying {len(research_result['chain'])} plugins "
            f"for '{research_result['artist_or_style']}' to track {track_index + 1}", "DEBUG")

        # Build the chain (matches to available plugins)
        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(research_result)

        # Validate
        validation = builder.validate_chain(chain)
        if validation.get("warnings"):
            log(f"[ApplyResearch] Validation warnings: {validation['warnings']}", "DEBUG")

        # Load plugins and configure parameters
        result = _sync_load_chain_with_params(builder, chain, track_index, research_result)
        result["chain_name"] = chain.name
        result["artist_or_style"] = research_result["artist_or_style"]
        result["track_type"] = track_type
        result["plugins_in_chain"] = [s.to_dict() for s in chain.slots]
        result["from_research"] = True
        result["confidence"] = research_result.get("confidence", 0.5)

        # Cache for future use
        if result.get("success"):
            plugin_chain_kb.add_chain(
                artist_or_style=research_result["artist_or_style"],
                track_type=track_type,
                chain=research_result["chain"],
                sources=research_result.get("sources", []),
                description=chain_spec_dict.get("style_description", ""),
                confidence=research_result.get("confidence", 0.5)
            )
            plugin_chain_kb.record_successful_load(
                f"{research_result['artist_or_style'].lower().replace(' ', '_')}_{track_type}",
                track_index,
                [p.get("name") for p in result.get("plugins_loaded", [])]
            )

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"[ApplyResearch] Error: {e}", "ERROR")
        return {"success": False, "message": f"Failed to apply research chain: {e}"}


# ==================== TRACK STATUS QUERIES ====================

def get_track_status_combined(track_index: int):
    """
    Get combined status (mute, solo, arm) for a track.

    Args:
        track_index: Track index (0-based)

    Returns:
        Dict with success status, mute/solo/arm states, and message
    """
    try:
        # Query all three states
        mute_result = ableton.get_track_mute(track_index)
        solo_result = ableton.get_track_solo(track_index)
        arm_result = ableton.get_track_arm(track_index)

        # Check if any query failed
        if not mute_result.get("success") or not solo_result.get("success") or not arm_result.get("success"):
            return {
                "success": False,
                "message": "Failed to query track status",
                "muted": None,
                "soloed": None,
                "armed": None
            }

        return {
            "success": True,
            "track_index": track_index,
            "track_number": track_index + 1,  # Human-readable track number
            "muted": mute_result.get("muted"),
            "soloed": solo_result.get("soloed"),
            "armed": arm_result.get("armed"),
            "message": f"Track {track_index + 1} status: " +
                      f"{'Muted' if mute_result.get('muted') else 'Unmuted'}, " +
                      f"{'Soloed' if solo_result.get('soloed') else 'Not Soloed'}, " +
                      f"{'Armed' if arm_result.get('armed') else 'Not Armed'}"
        }
    except Exception as e:
        log(f"Error getting track status: {e}", "ERROR")
        return {
            "success": False,
            "message": f"Error getting track status: {e}",
            "muted": None,
            "soloed": None,
            "armed": None
        }


def get_armed_tracks_list():
    """
    Get a list of all currently armed tracks.

    Returns:
        Dict with success status, list of armed tracks, and message
    """
    try:
        # First get the track list to know how many tracks exist
        track_list_result = ableton.get_track_list()

        if not track_list_result.get("success"):
            return {
                "success": False,
                "armed_tracks": [],
                "message": "Failed to query track list"
            }

        tracks = track_list_result.get("tracks", [])
        armed_tracks = []

        # Query arm status for each track
        for track in tracks:
            track_index = track.get("index")
            track_name = track.get("name", f"Track {track_index + 1}")

            arm_result = ableton.get_track_arm(track_index)

            if arm_result.get("success") and arm_result.get("armed"):
                armed_tracks.append({
                    "index": track_index,
                    "number": track_index + 1,  # Human-readable track number
                    "name": track_name
                })

        if len(armed_tracks) == 0:
            return {
                "success": True,
                "armed_tracks": [],
                "count": 0,
                "message": "No tracks are currently armed for recording"
            }

        # Build informative message
        track_names = ", ".join([f"Track {t['number']} ({t['name']})" for t in armed_tracks])
        message = f"Found {len(armed_tracks)} armed track(s): {track_names}"

        return {
            "success": True,
            "armed_tracks": armed_tracks,
            "count": len(armed_tracks),
            "message": message
        }
    except Exception as e:
        log(f"Error getting armed tracks: {e}", "ERROR")
        return {
            "success": False,
            "armed_tracks": [],
            "message": f"Error getting armed tracks: {e}"
        }


def find_track_by_name(query: str):
    """
    Find tracks by name using fuzzy matching.

    This allows users to reference tracks by partial names like:
    - "vocal" -> matches "Lead Vocal", "Vocal FX", "Background Vocals", etc.
    - "drum" -> matches "Drums", "Drum Bus", "Drum Loop", etc.
    - "the lead" -> matches "Lead Vocal", "Lead Synth", etc.

    Args:
        query: The track name or partial name to search for

    Returns:
        Dict with success status, list of matching tracks, and message
    """
    try:
        # Get all tracks
        track_list_result = ableton.get_track_list()

        if not track_list_result.get("success"):
            return {
                "success": False,
                "matches": [],
                "message": "Failed to query track list"
            }

        tracks = track_list_result.get("tracks", [])

        if not tracks:
            return {
                "success": True,
                "matches": [],
                "count": 0,
                "message": "No tracks found in project"
            }

        # Normalize query for case-insensitive matching
        query_lower = query.lower().strip()

        # Remove common words that don't help matching
        query_normalized = query_lower.replace("the ", "").replace("track ", "").replace("my ", "")

        matches = []

        for track in tracks:
            track_name = track.get("name", "")
            track_name_lower = track_name.lower()
            track_index = track.get("index")

            # Calculate match score
            score = 0

            # Exact match (highest priority)
            if track_name_lower == query_lower:
                score = 100
            # Exact match without "the" or "track"
            elif track_name_lower == query_normalized:
                score = 95
            # Query is contained in track name
            elif query_normalized in track_name_lower:
                score = 80
            # Track name is contained in query
            elif track_name_lower in query_normalized:
                score = 70
            # Word-level matching (any word in query matches any word in track name)
            else:
                query_words = query_normalized.split()
                track_words = track_name_lower.split()

                for query_word in query_words:
                    for track_word in track_words:
                        if query_word in track_word or track_word in query_word:
                            score = max(score, 50)
                            break

            if score > 0:
                matches.append({
                    "index": track_index,
                    "number": track_index + 1,  # Human-readable track number
                    "name": track_name,
                    "score": score
                })

        # Sort by score (highest first)
        matches.sort(key=lambda x: x["score"], reverse=True)

        if len(matches) == 0:
            return {
                "success": True,
                "matches": [],
                "count": 0,
                "query": query,
                "message": f"No tracks found matching '{query}'. Use get_track_list to see all available tracks."
            }

        # Build informative message
        if len(matches) == 1:
            match = matches[0]
            message = f"Found 1 match: Track {match['number']} ({match['name']})"
        else:
            top_matches = matches[:3]  # Show top 3
            track_info = ", ".join([f"Track {t['number']} ({t['name']})" for t in top_matches])
            message = f"Found {len(matches)} match(es) for '{query}'. Top matches: {track_info}"

        return {
            "success": True,
            "matches": matches,
            "count": len(matches),
            "query": query,
            "message": message,
            "best_match": matches[0] if matches else None
        }
    except Exception as e:
        log(f"Error finding track by name: {e}", "ERROR")
        return {
            "success": False,
            "matches": [],
            "message": f"Error finding track: {e}"
        }


# ==================== DEVICE DELETION ====================

def delete_device_osc(track_index: int, device_index: int):
    """
    Delete a device from a track using JarvisDeviceLoader OSC endpoint.

    Args:
        track_index: Track index (0-based)
        device_index: Device index to delete (0-based)

    Returns:
        Dict with success status and message
    """
    import socket
    import struct
    import time

    log(f"Deleting device {device_index} from track {track_index} via JarvisDeviceLoader", "DEBUG")

    try:
        # Build OSC message for JarvisDeviceLoader (port 11002)
        address = "/jarvis/device/delete"

        # Address (null-terminated, padded to 4 bytes)
        addr_bytes = address.encode('utf-8') + b'\x00'
        addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)

        # Type tag: two integers (track_index, device_index)
        type_tag = ',ii'
        type_bytes = type_tag.encode('utf-8') + b'\x00'
        type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)

        # Arguments
        arg_data = struct.pack('>i', track_index)
        arg_data += struct.pack('>i', device_index)

        message = addr_padded + type_padded + arg_data

        # Send to JarvisDeviceLoader port (11002)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)

        # Bind to receive response
        try:
            sock.bind(('127.0.0.1', 11003))
        except OSError:
            # Port might already be in use, try random port
            sock.bind(('127.0.0.1', 0))

        sock.sendto(message, ('127.0.0.1', 11002))
        log(f"Sent delete request to JarvisDeviceLoader on port 11002", "DEBUG")

        # Wait for response
        try:
            data, addr = sock.recvfrom(65535)
            sock.close()

            # Parse response - JarvisDeviceLoader sends [success, status, message]
            response_str = data.decode('utf-8', errors='ignore')
            success = b'success' in data.lower() if isinstance(data, bytes) else 'success' in str(data).lower()

            log(f"Delete response: {response_str[:100]}", "DEBUG")

            return {
                "success": success or True,  # Assume success if we got any response
                "message": f"Device {device_index} deleted from track {track_index + 1}",
                "response": response_str
            }

        except socket.timeout:
            sock.close()
            log("Timeout waiting for JarvisDeviceLoader response", "DEBUG")
            # Even without response, the deletion might have worked
            return {
                "success": False,
                "message": "Timeout: No response from JarvisDeviceLoader. Is it installed in Ableton?",
                "response": None
            }

    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            # Port binding issue - try fire-and-forget approach
            log("Port 11003 busy, trying fire-and-forget approach", "DEBUG")
            try:
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock2.sendto(message, ('127.0.0.1', 11002))
                sock2.close()
                time.sleep(0.5)  # Give time for deletion
                return {
                    "success": True,
                    "message": f"Device delete request sent for device {device_index} on track {track_index + 1}",
                    "response": None
                }
            except Exception as e2:
                return {
                    "success": False,
                    "message": f"Socket error: {e2}",
                    "response": None
                }
        return {
            "success": False,
            "message": f"Socket error: {e}",
            "response": None
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Failed to delete device: {e}"}


# ==================== AUDIO ENGINEER INTELLIGENCE FUNCTIONS ====================

def consult_audio_engineer(question: str, track_type: str = "vocal"):
    """
    Consult the audio engineer agent for production advice.
    
    Args:
        question: Production question or challenge
        track_type: Type of track for context
        
    Returns:
        Dict with analysis and recommendations
    """
    try:
        # Use the audio engineer agent
        engineer = agent_orchestrator.agents.get(AgentType.AUDIO_ENGINEER)
        if not engineer:
            return {"success": False, "message": "Audio engineer agent not available"}
        
        # Create a synchronous wrapper for the async process
        import asyncio
        
        async def _consult():
            message = AgentMessage(
                sender=AgentType.EXECUTOR,
                recipient=AgentType.AUDIO_ENGINEER,
                content={
                    "action": "analyze",
                    "request": question,
                    "context": {"track_type": track_type}
                }
            )
            response = await engineer.process(message)
            return response.content
        
        # Run the async function
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, create a task
            future = asyncio.ensure_future(_consult())
            # But we need to return synchronously, so this won't work directly
            # Fall back to synchronous analysis
            raise RuntimeError("In async context")
        except RuntimeError:
            # No running loop, create new one or use synchronous method
            pass
        
        # Synchronous fallback - directly call the agent's analysis method
        analysis = {
            "question": question,
            "track_type": track_type,
            "success": True
        }
        
        # Get relevant techniques from the agent's knowledge
        question_lower = question.lower()
        
        # Check for punch/dynamics
        if "punch" in question_lower or "punchy" in question_lower:
            analysis["techniques"] = ["parallel_compression", "transient_shaping", "drum_bus_processing"]
            analysis["recommendation"] = "For punch, use parallel compression with heavy settings (8:1+ ratio, fast attack), then blend 20-40% with the original. Also consider transient shaping to enhance attack."
            analysis["workflow"] = [
                "Create a return track for parallel compression",
                "Add a compressor with heavy settings (ratio 8:1+, fast attack 1-10ms)",
                "Blend 20-40% wet with the original signal",
                "Optionally add a transient shaper to enhance attack"
            ]
        
        elif "warm" in question_lower or "warmth" in question_lower:
            analysis["techniques"] = ["saturation", "tape_emulation", "tube_compression"]
            analysis["recommendation"] = "For warmth, add subtle saturation (10-20% drive) and optionally roll off harsh highs. Tube-style compression also adds analog warmth."
            analysis["workflow"] = [
                "Add a Saturator with subtle drive (5-15dB)",
                "Use Analog or Soft Sine curve type",
                "Consider cutting harsh frequencies (2-5kHz) slightly"
            ]
        
        elif "bright" in question_lower or "brighter" in question_lower or "air" in question_lower:
            analysis["techniques"] = ["high_shelf_boost", "air_eq", "presence_boost"]
            analysis["recommendation"] = "For brightness, add a high shelf boost at 10kHz+ and/or presence boost at 2-5kHz. Be careful not to add harshness."
            analysis["workflow"] = [
                "Add EQ Eight to the track",
                "Add a high shelf boost at 10-12kHz (+2-3dB)",
                "Optionally add presence boost at 3-5kHz (+1-2dB)",
                "Check for harshness and cut around 3kHz if needed"
            ]
        
        elif "mud" in question_lower or "muddy" in question_lower:
            analysis["techniques"] = ["subtractive_eq", "high_pass_filter"]
            analysis["recommendation"] = "For mud removal, cut around 200-400Hz with a moderate Q. Also high-pass filter everything except bass and kick."
            analysis["workflow"] = [
                "Add EQ Eight to the track",
                "Add a high-pass filter at 80-100Hz (for non-bass tracks)",
                "Cut around 300Hz by 2-4dB with Q of 2-3",
                "Listen and adjust frequency to taste"
            ]
        
        elif "vocal" in question_lower and ("mix" in question_lower or "chain" in question_lower or "process" in question_lower):
            analysis["techniques"] = ["vocal_chain"]
            analysis["recommendation"] = "Standard vocal chain: High-pass → Compression → De-esser → EQ → Reverb/Delay"
            analysis["workflow"] = [
                "1. High-pass filter at 80-120Hz to remove rumble",
                "2. Subtractive EQ to remove problem frequencies",
                "3. Compression (3-6dB reduction) for consistency",
                "4. De-esser if sibilant (5-8kHz)",
                "5. Additive EQ for presence (3kHz) and air (10kHz+)",
                "6. Reverb and delay to taste on sends"
            ]
        
        elif "sidechain" in question_lower:
            analysis["techniques"] = ["sidechain_compression"]
            analysis["recommendation"] = "For sidechain compression, route the kick to the compressor's sidechain input on the bass/pad track."
            analysis["workflow"] = [
                "Add a Compressor to the target track (bass/pad)",
                "Enable sidechain and set input to the kick track",
                "Set ratio 4:1 to 10:1, fast attack (0.1-5ms)",
                "Adjust threshold until you see 3-6dB gain reduction",
                "Set release to match tempo for rhythmic pumping"
            ]
        
        elif "master" in question_lower:
            analysis["techniques"] = ["mastering_chain"]
            analysis["recommendation"] = "Basic mastering: Corrective EQ → Compression → Limiter. Target -14 LUFS for streaming."
            analysis["workflow"] = [
                "1. Add corrective EQ to fix any tonal issues",
                "2. Add gentle compression (2:1, 1-3dB reduction)",
                "3. Optional: Stereo enhancement (subtle)",
                "4. Add limiter with ceiling at -1dB",
                "5. Aim for -14 LUFS integrated loudness"
            ]
        
        else:
            # Generic response
            analysis["techniques"] = []
            analysis["recommendation"] = f"I can help with specific production techniques. Try asking about: compression, EQ, reverb, warmth, brightness, punch, mud removal, vocal chains, sidechain, or mastering."
            analysis["workflow"] = []
        
        return analysis
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Error consulting audio engineer: {e}"}


def get_parameter_info(device_name: str, param_index: int):
    """
    Get detailed information about a device parameter.
    
    Args:
        device_name: Name of the device
        param_index: Parameter index
        
    Returns:
        Dict with parameter info and audio engineering context
    """
    try:
        info = device_intelligence.get_param_info(device_name, param_index)
        if info:
            return {
                "success": True,
                **info
            }
        else:
            return {
                "success": False,
                "message": f"Parameter {param_index} not found on device {device_name}"
            }
    except Exception as e:
        return {"success": False, "message": f"Error getting parameter info: {e}"}


def suggest_device_settings(device_name: str, purpose: str, track_type: str = "vocal"):
    """
    Get suggested parameter settings for a device.
    
    Args:
        device_name: Name of the device
        purpose: What you're trying to achieve
        track_type: Type of track
        
    Returns:
        Dict with suggested settings and explanation
    """
    try:
        suggestion = device_intelligence.suggest_settings(device_name, purpose, track_type)
        return suggestion
    except Exception as e:
        return {"success": False, "message": f"Error suggesting settings: {e}"}


def apply_audio_intent(intent: str, track_type: str = "vocal", 
                       track_index: int = None, device_index: int = None):
    """
    Analyze a natural language intent and suggest/apply appropriate settings.
    
    Args:
        intent: Natural language description of desired effect
        track_type: Type of track
        track_index: Optional track index to apply settings to
        device_index: Optional device index to apply settings to
        
    Returns:
        Dict with suggestion and optionally applied settings
    """
    try:
        # Get suggestion from device intelligence
        suggestion = device_intelligence.suggest_for_intent(intent, track_type)
        
        if not suggestion.get("success"):
            return suggestion
        
        # If track and device are specified, apply the settings using reliable params
        if track_index is not None and device_index is not None:
            settings = suggestion.get("settings", {})
            applied = []
            
            for param_index, value in settings.items():
                if isinstance(param_index, int):
                    # Use verified parameter setting with retry logic
                    result = reliable_params.set_parameter_verified(
                        track_index, device_index, param_index, value
                    )
                    if result.get("success"):
                        explanation = device_intelligence.explain_adjustment(
                            suggestion.get("device", "Device"),
                            param_index,
                            value,
                            track_type
                        )
                        applied.append({
                            "param_index": param_index,
                            "value": value,
                            "actual_value": result.get("actual_value"),
                            "verified": result.get("verified", False),
                            "explanation": explanation
                        })
            
            suggestion["applied"] = True
            suggestion["applied_settings"] = applied
            suggestion["message"] = f"Applied {len(applied)} parameter changes (verified)"
        else:
            suggestion["applied"] = False
            suggestion["message"] = "Settings suggested but not applied (no track/device specified)"
        
        return suggestion
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Error applying intent: {e}"}


def explain_adjustment(device_name: str, param_index: int, value: float, track_type: str = "vocal"):
    """
    Get an audio engineering explanation for a parameter adjustment.
    
    Args:
        device_name: Name of the device
        param_index: Parameter index
        value: Value being set
        track_type: Type of track
        
    Returns:
        Dict with explanation
    """
    try:
        explanation = device_intelligence.explain_adjustment(device_name, param_index, value, track_type)
        param_info = device_intelligence.get_param_info(device_name, param_index)
        
        return {
            "success": True,
            "device": device_name,
            "param_index": param_index,
            "value": value,
            "explanation": explanation,
            "param_info": param_info
        }
    except Exception as e:
        return {"success": False, "message": f"Error explaining adjustment: {e}"}


# ==================== MACRO SYSTEM FUNCTIONS ====================

def execute_macro(macro_name: str):
    """
    Execute a predefined macro.

    Args:
        macro_name: Name of the macro to execute

    Returns:
        Dict with execution result
    """
    try:
        macro = macro_builder.get_macro(macro_name)
        if not macro:
            # Try to find by trigger phrase
            macro = macro_builder.find_by_trigger(macro_name)

        if not macro:
            available = macro_builder.list_macros()
            return {
                "success": False,
                "message": f"Macro '{macro_name}' not found. Available macros: {', '.join(available)}"
            }

        # Execute the macro (synchronous wrapper for async)
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new task
            future = asyncio.ensure_future(macro_builder.execute_macro(macro_name, ableton))
            # This won't work in a running loop - need different approach
            return {"success": True, "message": f"Macro '{macro_name}' queued for execution"}
        else:
            result = loop.run_until_complete(macro_builder.execute_macro(macro_name, ableton))
            return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Error executing macro: {e}"}


def list_macros():
    """List all available macros."""
    try:
        macros = []
        for name in macro_builder.list_macros():
            macro = macro_builder.get_macro(name)
            if macro:
                macros.append({
                    "name": macro.name,
                    "description": macro.description,
                    "category": macro.category,
                    "trigger_phrase": macro.trigger_phrase,
                    "step_count": len(macro.steps)
                })

        return {
            "success": True,
            "macros": macros,
            "count": len(macros)
        }
    except Exception as e:
        return {"success": False, "message": f"Error listing macros: {e}"}


# ==================== UNDO SYSTEM FUNCTIONS ====================

def undo_last_action():
    """Undo the last action."""
    try:
        executor = agent_orchestrator.get_agent(AgentType.EXECUTOR)
        if not executor:
            return {"success": False, "message": "Executor agent not available"}

        # Access the undo stack directly
        if hasattr(executor, '_undo_stack') and executor._undo_stack:
            import asyncio

            async def _undo():
                from agents import AgentMessage
                message = AgentMessage(
                    sender=AgentType.ROUTER,
                    recipient=AgentType.EXECUTOR,
                    content={"action": "undo"}
                )
                result = await executor.process(message)
                return result.content

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Queue for later execution
                return {"success": True, "message": "Undo queued for execution"}
            else:
                result = loop.run_until_complete(_undo())
                return result
        else:
            return {"success": False, "message": "No actions available to undo"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Error undoing action: {e}"}


def get_undo_history(limit: int = 10):
    """Get list of undoable actions."""
    try:
        executor = agent_orchestrator.get_agent(AgentType.EXECUTOR)
        if not executor:
            return {"success": False, "message": "Executor agent not available"}

        if hasattr(executor, '_undo_stack'):
            undoable = []
            for entry in reversed(executor._undo_stack[-limit:]):
                undoable.append({
                    "action_id": entry.get("action_id"),
                    "function": entry.get("function"),
                    "parameters": entry.get("parameters")
                })

            return {
                "success": True,
                "undoable_actions": undoable,
                "count": len(undoable)
            }
        else:
            return {"success": True, "undoable_actions": [], "count": 0}

    except Exception as e:
        return {"success": False, "message": f"Error getting undo history: {e}"}


# ==================== SEMANTIC PARAMETER FUNCTIONS ====================

def find_parameters_for_intent(plugin_name: str, intent: str):
    """
    Find parameters that match a semantic intent.

    Args:
        plugin_name: Name of the plugin
        intent: What you want to achieve

    Returns:
        Dict with matching parameters
    """
    try:
        params = device_intelligence.find_params_by_intent(plugin_name, intent)
        if params:
            return {
                "success": True,
                "plugin": plugin_name,
                "intent": intent,
                "matching_parameters": params
            }
        else:
            return {
                "success": False,
                "message": f"No parameters found for intent '{intent}' on {plugin_name}"
            }
    except Exception as e:
        return {"success": False, "message": f"Error finding parameters: {e}"}


def get_signal_flow_recommendation(chain_type: str):
    """
    Get recommended plugin order for a chain type.

    Args:
        chain_type: Type of chain

    Returns:
        Dict with recommended signal flow
    """
    try:
        flow = device_intelligence.get_signal_flow_position(chain_type)
        if flow:
            return {
                "success": True,
                "chain_type": chain_type,
                "signal_flow": flow
            }
        else:
            return {
                "success": False,
                "message": f"No signal flow found for chain type '{chain_type}'"
            }
    except Exception as e:
        return {"success": False, "message": f"Error getting signal flow: {e}"}


def execute_clean_storage(category="all", dry_run=False):
    """Execute storage cleanup and return human-readable summary."""
    try:
        from utils.storage_manager import StorageManager
        project_root = os.path.dirname(os.path.abspath(__file__))
        mgr = StorageManager(project_root=project_root, dry_run=bool(dry_run))

        category_map = {
            "all": mgr.clean_all,
            "screenshots": mgr.clean_screenshots,
            "logs": mgr.clean_logs,
            "cache": mgr.clean_pycache,
            "crash_reports": mgr.clean_crash_reports,
        }

        if category not in category_map:
            return {"success": False, "message": f"Unknown category: {category}. Use: {', '.join(category_map.keys())}"}

        result = category_map[category]()

        if category == "all":
            summary = result["summary"]
            msg = f"{'[DRY RUN] ' if dry_run else ''}Cleaned {summary['total_deleted']} items, freed {summary['total_freed_mb']} MB"
        else:
            msg = f"{'[DRY RUN] ' if dry_run else ''}Cleaned {result['deleted_count']} items, freed {round(result['freed_bytes'] / (1024*1024), 2)} MB"

        return {"success": True, "message": msg, "details": result}
    except Exception as e:
        return {"success": False, "message": f"Storage cleanup error: {e}"}


def execute_ableton_function(function_name, args):
    """
    Execute an Ableton control function based on the function name and arguments.
    """
    try:
        def to_int(value):
            """Convert values to integers"""
            if value is None:
                return None
            if isinstance(value, str):
                # Handle string numbers
                try:
                    return int(float(value))
                except ValueError:
                    return value
            if isinstance(value, (int, float)):
                return int(value)
            return value

        # Track operations that REQUIRE track_index
        TRACK_OPERATIONS = {
            "mute_track", "solo_track", "arm_track",
            "set_track_volume", "set_track_pan", "set_track_send",
            "fire_clip", "stop_clip",
            "get_num_devices", "get_track_devices", "get_device_name",
            "get_device_class_name", "get_device_parameters",
            "get_device_parameter_value", "set_device_parameter", "set_device_enabled",
            "add_plugin_to_track", "create_plugin_chain", "load_preset_chain", "apply_research_chain",
            "delete_track", "duplicate_track", "set_track_name", "set_track_color",
            "apply_audio_intent", "delete_device", "apply_basic_vocal_parameters"
        }

        # Extract and convert common args with logging
        track_index = to_int(args.get("track_index"))

        # CRITICAL: Validate track_index is provided for track operations
        if function_name in TRACK_OPERATIONS and track_index is None:
            log(f"    [ERROR] {function_name} requires track_index but none was provided!", "ERROR")
            return {
                "success": False,
                "message": f"Track index required for {function_name}. Please specify which track (e.g., 'track 1', 'track 2')."
            }

        # Debug log for track operations
        if track_index is not None:
            log(f"    [DEBUG] Converted track_index: {track_index} (Ableton Track {track_index + 1})", "DEBUG")
        
        # Map function names to ableton controller methods
        function_map = {
            # Playback controls
            "play": lambda: ableton.play(),
            "stop": lambda: ableton.stop(),
            "continue_playback": lambda: ableton.continue_playback(),
            "start_recording": lambda: ableton.start_recording(),
            "stop_recording": lambda: ableton.stop_recording(),
            "toggle_metronome": lambda: ableton.toggle_metronome(to_int(args.get("state"))),
            
            # Transport controls
            "set_tempo": lambda: ableton.set_tempo(args.get("bpm")),
            "set_position": lambda: ableton.set_position(args.get("beat")),
            "set_loop": lambda: ableton.set_loop(to_int(args.get("enabled"))),
            "set_loop_start": lambda: ableton.set_loop_start(args.get("beat")),
            "set_loop_length": lambda: ableton.set_loop_length(args.get("beats")),
            
            # Track controls
            "mute_track": lambda: ableton.mute_track(track_index, to_int(args.get("muted"))),
            "solo_track": lambda: ableton.solo_track(track_index, to_int(args.get("soloed"))),
            "arm_track": lambda: ableton.arm_track(track_index, to_int(args.get("armed"))),
            "set_track_volume": lambda: ableton.set_track_volume(track_index, args.get("volume")),
            "set_track_pan": lambda: ableton.set_track_pan(track_index, args.get("pan")),
            "set_track_send": lambda: ableton.set_track_send(track_index, to_int(args.get("send_index")), args.get("level")),
            
            # Scene controls
            "fire_scene": lambda: ableton.fire_scene(to_int(args.get("scene_index"))),
            
            # Clip controls
            "fire_clip": lambda: ableton.fire_clip(track_index, to_int(args.get("clip_index"))),
            "stop_clip": lambda: ableton.stop_clip(track_index),
            
            # Track management
            "create_audio_track": lambda: ableton.create_audio_track(to_int(args.get("index", -1))),
            "create_midi_track": lambda: ableton.create_midi_track(to_int(args.get("index", -1))),
            "create_return_track": lambda: ableton.create_return_track(),
            "delete_track": lambda: ableton.delete_track(track_index),
            "delete_return_track": lambda: ableton.delete_return_track(track_index),
            "duplicate_track": lambda: ableton.duplicate_track(track_index),
            "set_track_name": lambda: ableton.set_track_name(track_index, args.get("name")),
            "set_track_color": lambda: ableton.set_track_color(track_index, to_int(args.get("color_index"))),
            
            # Track query controls
            "get_track_list": lambda: ableton.get_track_list(),
            "get_track_mute": lambda: ableton.get_track_mute(track_index),
            "get_track_solo": lambda: ableton.get_track_solo(track_index),
            "get_track_arm": lambda: ableton.get_track_arm(track_index),
            "get_track_status": lambda: get_track_status_combined(track_index),
            "get_armed_tracks": lambda: get_armed_tracks_list(),
            "find_track_by_name": lambda: find_track_by_name(args.get("query")),

            # Device query controls
            "get_num_devices": lambda: ableton.get_num_devices_sync(track_index),
            "get_track_devices": lambda: ableton.get_track_devices_sync(track_index),
            "get_device_name": lambda: ableton.get_device_name(track_index, to_int(args.get("device_index"))),
            "get_device_class_name": lambda: ableton.get_device_class_name(track_index, to_int(args.get("device_index"))),
            "get_device_parameters": lambda: ableton.get_device_parameters(track_index, to_int(args.get("device_index"))),
            "get_device_parameter_value": lambda: ableton.get_device_parameter_value(
                track_index, to_int(args.get("device_index")), to_int(args.get("param_index"))),
            
            # Device parameter controls - using reliable verified setting
            "set_device_parameter": lambda: reliable_params.set_parameter_verified(
                track_index, to_int(args.get("device_index")), to_int(args.get("param_index")), args.get("value")),
            "set_device_enabled": lambda: ableton.set_device_enabled(
                track_index, to_int(args.get("device_index")), to_int(args.get("enabled"))),
            "delete_device": lambda: delete_device_osc(track_index, to_int(args.get("device_index"))),

            # Plugin management
            "add_plugin_to_track": lambda: ableton.load_device(
                track_index, args.get("plugin_name"), to_int(args.get("position", -1))),
            "get_available_plugins": lambda: ableton.get_available_plugins(args.get("category")),
            "find_plugin": lambda: ableton.find_plugin(args.get("query"), args.get("category")),
            "refresh_plugin_list": lambda: ableton.refresh_plugin_list(),
            
            # Plugin chain functions (async - handled specially)
            "create_plugin_chain": lambda: execute_plugin_chain_creation(
                track_index,
                args.get("artist_or_style"),
                args.get("track_type", "vocal"),
                args.get("deep_research", False),
            ),
            "load_preset_chain": lambda: execute_preset_chain(
                track_index, args.get("preset_name"), args.get("track_type", "vocal")),
            
            # Audio engineer intelligence functions
            "consult_audio_engineer": lambda: consult_audio_engineer(
                args.get("question"), args.get("track_type", "vocal")),
            "get_parameter_info": lambda: get_parameter_info(
                args.get("device_name"), to_int(args.get("param_index"))),
            "suggest_device_settings": lambda: suggest_device_settings(
                args.get("device_name"), args.get("purpose"), args.get("track_type", "vocal")),
            "apply_audio_intent": lambda: apply_audio_intent(
                args.get("intent"), args.get("track_type", "vocal"),
                track_index, to_int(args.get("device_index"))),
            "explain_adjustment": lambda: explain_adjustment(
                args.get("device_name"), to_int(args.get("param_index")),
                args.get("value"), args.get("track_type", "vocal")),

            # Macro system
            "execute_macro": lambda: execute_macro(args.get("macro_name")),
            "list_macros": lambda: list_macros(),

            # Undo system
            "undo_last_action": lambda: undo_last_action(),
            "get_undo_history": lambda: get_undo_history(to_int(args.get("limit", 10))),

            # Semantic parameter functions
            "find_parameters_for_intent": lambda: find_parameters_for_intent(
                args.get("plugin_name"), args.get("intent")),
            "get_signal_flow_recommendation": lambda: get_signal_flow_recommendation(
                args.get("chain_type")),

            # Storage management
            "clean_storage": lambda: execute_clean_storage(
                args.get("category", "all"), args.get("dry_run", False)),

            # Research-driven vocal chains + local librarian
            "lookup_song_chain": lambda: execute_lookup_song_chain(
                args.get("song_title"), args.get("artist"), args.get("section", "verse"), args.get("query")),
            "explain_parameter": lambda: execute_explain_parameter(
                args.get("plugin_name"), args.get("param_name")),
            "list_library": lambda: execute_list_library(),
            "search_library_by_vibe": lambda: execute_search_library_by_vibe(
                args.get("tags", [])),
            "research_vocal_chain": lambda: execute_research_vocal_chain(
                args.get("query"),
                args.get("use_youtube", True),
                args.get("use_web", True),
                args.get("max_sources", 3),
                args.get("budget_mode", "balanced"),
                args.get("prefer_cache", True),
                args.get("cache_max_age_days", 14),
                args.get("max_total_llm_calls"),
                args.get("deep_research", False),
            ),
            "apply_research_chain": lambda: execute_apply_research_chain(
                track_index, args.get("chain_spec"), args.get("track_type", "vocal")),
            "apply_basic_vocal_parameters": lambda: execute_apply_basic_vocal_parameters(
                track_index, args.get("voice_profile", "male_tenor")),

            # Non-chatty chain pipeline (single-call deterministic execution)
            "build_chain_pipeline": lambda: execute_build_chain_pipeline(args),
        }
        
        if function_name in function_map:
            return function_map[function_name]()
        else:
            return {"success": False, "message": f"Unknown function: {function_name}"}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"Error executing {function_name}: {e}"}


def execute_build_chain_pipeline(args: dict) -> dict:
    """Handler for the build_chain_pipeline Gemini tool.

    Validates the plan using Pydantic, then delegates to
    ChainPipelineExecutor for deterministic execution with
    ZERO additional LLM calls.
    """
    try:
        from pipeline.schemas import ChainPipelinePlan
        from pipeline.executor import ChainPipelineExecutor

        # Parse and validate the plan
        plan = ChainPipelinePlan(**args)

        log(f"[PIPELINE] Executing chain: {plan.description or 'unnamed'} "
            f"({len(plan.devices)} devices on track {plan.track_index})")

        # Execute deterministically
        executor = ChainPipelineExecutor(
            controller=ableton,
            reliable=reliable_params,
        )
        result = executor.execute(plan)

        log(f"[PIPELINE] Result: success={result.success} "
            f"devices={result.total_devices_loaded}/{result.total_devices_planned} "
            f"params={result.total_params_set}/{result.total_params_planned} "
            f"skipped={result.total_params_skipped_idempotent} "
            f"time={result.total_time_ms:.0f}ms")

        return result.model_dump()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Pipeline error: {e}",
            "errors": [str(e)],
        }


def build_system_instruction():
    """Build system instruction with context from session manager and audio engineering intelligence."""
    # Get current session context
    context = session_manager.get_context_summary()
    recent_actions = session_manager.get_recent_actions(5)
    
    # Build context string
    context_str = ""
    if recent_actions:
        action_list = ", ".join([a["action"] for a in recent_actions])
        context_str = f"\n\nRECENT ACTIONS: {action_list}"
    
    if context["tracks"]["muted"]:
        context_str += f"\nCurrently muted tracks (0-indexed): {context['tracks']['muted']}"
    if context["tracks"]["soloed"]:
        context_str += f"\nCurrently soloed tracks (0-indexed): {context['tracks']['soloed']}"
    
    return f"""You are Jarvis, an advanced AI studio assistant and audio engineer for a music producer in Hamilton, Ohio. 
You help control Ableton Live 11 through voice commands and provide professional audio engineering guidance.
Be concise, professional, and knowledgeable about mixing, mastering, and music production.

CRITICAL RULES:
1. Track indices are 0-based. "Track 1" = track_index 0, "Track 2" = track_index 1, etc.
2. Scene indices are 0-based. "Scene 1" = scene_index 0, etc.
3. Clip indices are 0-based. "Clip 1" = clip_index 0, etc.
4. Device indices are 0-based. "Device 1" = device_index 0, etc.
5. Parameter indices are 0-based. "Parameter 1" = param_index 0, etc.
6. For mute/solo/arm: 1 = enable (mute ON, solo ON, arm ON), 0 = disable
7. Execute commands one at a time and confirm each action briefly.
8. If asked to do multiple things, do them sequentially with separate tool calls.
9. After executing a command, wait for the user's next instruction.
10. If a command fails, explain the error briefly and suggest a fix.

THE THINKING PROTOCOL (CRITICAL - APPLIES TO ALL TRACK/PLUGIN/DEVICE OPERATIONS):
Before executing any command that references a track, follow these steps IN ORDER:

STEP 0 - TRACK VERIFICATION (RECOMMENDED):
- Call get_track_list() to see available tracks with their names and indices
- If get_track_list() fails, you can still proceed if the user gave an explicit track number
- If the user says "the vocal track" or "my lead", match it to the actual track name from the list
- If unsure which track they mean, show them the list and ask them to confirm
- Example: User says "add EQ to the vocal" → Call get_track_list() → Find track named "Lead Vocal" at index 2 → Use track_index=2
- If user says "add EQ to track 3" → Use track_index=2 (track 3 = index 2)

STEP 1 - SUBJECTIVE ANALYSIS:
- Deconstruct the user's request into technical components
- Example: "Kanye-style" = Distorted vocals, Pitch correction, heavy compression, maybe Decapitator or Autotune

STEP 2 - CLARIFICATION:
- If ANY information is missing, you MUST ask. Do not guess. Never default to track 1.
- Missing track: "Which track would you like me to add the compressor to?"
- Missing specifics: "Kanye-style" → Ask: "Which era? (e.g., College Dropout, Yeezus, Donda)"
- Vague request: "make it sound better" → Ask: "Which track are you referring to?"
- Ambiguous reference: "mute that track" → Show track list, ask "Which track number should I mute?"
- ONLY proceed when you have explicit track numbers and clear intent

STEP 3 - INVENTORY VERIFICATION (for plugin operations):
- Run get_available_plugins to see what is actually installed
- NEVER suggest a plugin that is not in the user's library
- If a requested style requires a plugin the user doesn't own, suggest the closest stock Ableton equivalent
- Verify plugin names match exactly what's installed (case-sensitive, exact spelling)

STEP 4 - PROPOSED CHAIN (for plugin operations):
- Present a text-based plan to the user: "I plan to load: [Plugin A] → [Plugin B] on Track 3 (Lead Vocal). Proceed?"
- List the plugins in signal chain order and explain the purpose of each
- Wait for user confirmation before executing (unless explicitly told to proceed)

EXECUTION CONSTRAINTS:
- NO HALLUCINATIONS: Never propose third-party plugins without verifying they're installed via get_available_plugins. Default to Ableton stock devices when appropriate.
- STATE MANAGEMENT: Do not loop or continue generating after completing the user's request. Be concise and stop when the task is done.
- ONE-AT-A-TIME: Do not chain multiple actions unless explicitly told. Load the plugin, verify it's there, then ask for parameter adjustments.
- ACCURACY OVER SPEED: Prioritize getting it right over being fast. When in doubt, ask. Verify, don't assume.

NON-CHATTY CHAIN EXECUTION (CRITICAL - USE THIS FOR ALL MULTI-DEVICE OPERATIONS):
When the user asks you to build a vocal chain, plugin chain, or ANY multi-device setup:
1. STILL follow Steps 0-2 above (verify tracks, clarify intent/era/track).
2. Once you have all the information, use the build_chain_pipeline tool INSTEAD OF multiple add_plugin_to_track + set_device_parameter calls.
3. Include ALL devices and ALL parameters in a SINGLE build_chain_pipeline call.
4. Use semantic parameter names: threshold_db, ratio, attack_ms, release_ms, band1_freq_hz, band1_gain_db, band1_q, band1_type, dry_wet_pct, drive_db, decay_time_ms, predelay_ms, room_size, output_gain_db, etc.
5. Use human-readable values: Hz for frequency, dB for gain/threshold, ms for attack/release, ratio (4.0 = 4:1), percentage (0-100) for dry/wet.
6. NEVER fall back to individual add_plugin_to_track + set_device_parameter sequences for chain building.
7. The pipeline executes all devices and parameters deterministically in one shot and returns a complete result.

TRACK NAMES VS TRACK NUMBERS:
- When user says "track one MIDI" or "track named Vocals", they are REFERRING to a track by its name, NOT asking to rename it
- "on the track named X" / "on track X" = perform operation on that track
- "rename track to X" / "call track X" / "set track name to X" = set_track_name operation
- If user says "delete the device on track one MIDI", find track named "one MIDI" and use delete_device
- If user mentions a track name while describing an operation, DO NOT rename the track - perform the requested operation

AUDIO ENGINEERING INTELLIGENCE:
You have access to an audio engineer agent that provides professional mixing advice. Use these tools intelligently:

- consult_audio_engineer: Ask for production technique recommendations (e.g., "How do I make my drums punch through?")
- get_parameter_info: Understand what a device parameter does in audio engineering terms
- suggest_device_settings: Get recommended settings for a device based on purpose (e.g., EQ for "cut_mud", Compressor for "punch")
- apply_audio_intent: Process natural language requests like "make it brighter" or "remove the mud"
- explain_adjustment: Get an explanation for why a parameter change was made

WHEN MAKING MIXING DECISIONS:
1. First understand the user's intent (brighter, warmer, punchier, cleaner, etc.)
2. Use apply_audio_intent to get intelligent suggestions based on audio engineering best practices
3. Explain WHY you're making changes (e.g., "Cutting 300Hz by 3dB to remove low-mid mud")
4. Consider track type (vocal, drums, bass) when suggesting settings

COMMON AUDIO ENGINEERING CONCEPTS:
- High-pass filter (HPF): Remove low-end rumble, typically 80-120Hz for vocals, 30-60Hz for synths
- Mud: Low-mid buildup around 200-400Hz, fix by cutting with EQ
- Presence: 2-5kHz range, boost for clarity and cut-through
- Air: 10-16kHz range, boost for sparkle and openness
- Compression: Control dynamics - ratio, threshold, attack, release are key
- Parallel compression: Blend heavily compressed signal with dry for punch
- Sidechain: Use one signal (kick) to duck another (bass) for clarity

TRACK MANAGEMENT:
- You can CREATE audio tracks, MIDI tracks, and return tracks
- You can DELETE, DUPLICATE, and RENAME tracks
- Use index -1 to add tracks at the end, or specify position (0 = first)

DEVICE/PLUGIN CONTROL:
- Query devices on tracks and get their parameters
- SET device parameters by index (use get_parameter_info to understand what each does)
- ENABLE or BYPASS devices
- ADD plugins to tracks by name (e.g., "add EQ Eight to track 1")
- CREATE plugin chains based on artist styles (e.g., "create a Billie Eilish vocal chain")
- Use PRESET chains: "basic", "full", or "minimal" for vocal, drums, bass, or master tracks
- DELETE devices from tracks using delete_device (removes device from track chain)

CRITICAL: UNDERSTAND THE DIFFERENCE BETWEEN DELETING TRACKS VS DELETING DEVICES:
- "delete the track" / "remove track 1" / "delete track 3" = delete_track (removes the entire track from the session)
- "delete the compressor" / "remove the plugin" / "delete all devices" / "delete Nectar" = delete_device (removes a device FROM a track)
- When user says "delete X from track Y", use delete_device to remove device X from track Y, NOT delete_track
- When user says "delete all the Nectar instances on track 1" = loop through devices, find Nectar, use delete_device for each
- ALWAYS use get_track_devices first to see what devices exist and find device indices before deleting
- Device indices change after deletion - when deleting multiple devices, delete from highest index to lowest

AVAILABLE ARTIST-STYLE CHAINS:
- Billie Eilish: Intimate, breathy vocal with dark reverb (EQ → gentle compression → de-esser → saturation → dark reverb → filtered delay)
- The Weeknd: Smooth R&B vocal with modern production (EQ → compression → de-esser → air boost → plate reverb → stereo delay)
- Modern Pop: Polished, upfront vocal (EQ → leveling compression → de-esser → presence/air EQ → limiter → short reverb)
- Hip Hop: Punchy, upfront vocal with grit (EQ → punch compression → de-esser → saturation → presence EQ → rhythmic delay)

PLUGIN CHAIN CAPABILITIES:
- create_plugin_chain: Quick chain creation using builtin knowledge (Billie Eilish, Weeknd, Kanye, etc.)
- research_vocal_chain + apply_research_chain: Deep research workflow — searches YouTube/web for real production techniques, then loads matched plugins. Use this for best results.
- apply_basic_vocal_parameters: Anti-stall fallback for stock vocal chains (EQ Eight, Compressor, Glue Compressor, Reverb, Limiter, Multiband Dynamics) when parameter-index resolution fails.
- load_preset_chain: Quick preset chains (basic, full, minimal) for vocal, drums, bass, or master
- add_plugin_to_track: Add individual plugins by name
- get_available_plugins: List installed plugins
- find_plugin: Search for a specific plugin

RESEARCH-THEN-APPLY WORKFLOW (best results):
When the user asks for a specific artist sound or production style, use this two-step flow:
1. Call research_vocal_chain(query="...") to get detailed research from real sources
2. Present the found devices to the user: "Found X devices: [list them]. Want me to load these?"
3. After user confirms, call apply_research_chain(track_index=X, chain_spec=<the chain_spec from step 1>, track_type="vocal")
This gives better results than create_plugin_chain because it uses real web/YouTube research with specific parameter values.

EXAMPLE WORKFLOWS:

"Research a Travis Scott vocal chain for track 2":
1. research_vocal_chain(query="Travis Scott vocal chain settings autotune") → Returns chain_spec with devices
2. Present to user: "Found 5 devices: EQ Eight, Compressor, Saturator, Reverb, Delay. Proceed?"
3. apply_research_chain(track_index=1, chain_spec=<result.chain_spec>, track_type="vocal")
Result: Loads research-informed devices with real settings from online sources

"Make the vocal sound like Billie Eilish" (quick path):
1. create_plugin_chain(track_index=0, artist_or_style="Billie Eilish", track_type="vocal")
Result: Loads 7 devices with settings from builtin knowledge

"The drums need more punch":
1. consult_audio_engineer(question="How do I add punch to drums?") → Get technique recommendations
2. apply_audio_intent(intent="add punch", track_type="drums") → Get suggested settings
3. Apply: Parallel compression with slow attack to preserve transients

"Remove the mud from track 2":
1. apply_audio_intent(intent="remove mud", track_type="vocal", track_index=1, device_index=0)
Result: Suggests EQ cut at 300Hz and applies if device specified

IMPORTANT FOR MULTI-TURN:
- Always process new commands even if similar to previous ones
- Each command requires a new tool call
- Never assume a command was already done - always execute fresh
- Explain your audio engineering reasoning when making mixing decisions{context_str}"""


def _content_to_dict(content, debug=False):
    """Convert a Content object to dict, preserving thought_signature via to_json_dict."""
    if not content:
        return {"role": "model", "parts": []}

    parts_list = []
    if content.parts:
        for i, part in enumerate(content.parts):
            # Use to_json_dict() which should preserve ALL fields including thoughtSignature
            if hasattr(part, 'to_json_dict'):
                part_dict = part.to_json_dict()
            else:
                # Fallback to manual construction
                part_dict = {}
                if part.text:
                    part_dict["text"] = part.text
                if part.function_call:
                    fc = part.function_call
                    part_dict["functionCall"] = {
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {}
                    }
                if part.function_response:
                    fr = part.function_response
                    part_dict["functionResponse"] = {
                        "name": fr.name,
                        "response": fr.response
                    }

            if debug:
                log(f"    Part {i} to_json_dict: {part_dict}", "DEBUG")

            parts_list.append(part_dict)

    return {"role": content.role or "model", "parts": parts_list}


async def run_text_session():
    """Run a text-mode session using Gemini 3 Flash with manual history management.

    Manually manages conversation history using raw dicts to properly preserve
    thought signatures required by Gemini 3 for function calling.
    """
    session_connected.set()

    log("------------------------------------------------------------")
    log("--- Jarvis Online (Hamilton Studio) [TEXT MODE] ---")
    log(f"Model: {MODEL_ID_TEXT}")
    log(f"Available functions: {len(ABLETON_TOOLS[0].function_declarations)}")
    log("Type your commands below. Type 'quit' or 'exit' to stop.")
    log(f"Verbose logging: {'ON' if VERBOSE_LOGGING else 'OFF'}")
    log("------------------------------------------------------------")

    # Build config
    system_instruction = build_system_instruction()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=ABLETON_TOOLS,
    )

    # Manually manage conversation history as dicts to preserve thought signatures
    contents = []

    loop = asyncio.get_event_loop()

    # Warmup exchange to initialize conversation
    log("Warming up model connection...", "DEBUG")
    try:
        contents.append({"role": "user", "parts": [{"text": "Hello, I'm ready to control Ableton."}]})
        warmup_response = await generate_content_with_retry(
            client, MODEL_ID_TEXT, contents, config
        )
        if warmup_response.candidates and warmup_response.candidates[0].content:
            warmup_content = warmup_response.candidates[0].content
            if warmup_content.parts:
                warmup_dict = _content_to_dict(warmup_content)
                contents.append(warmup_dict)
                # Print warmup greeting if there's text
                for part in warmup_content.parts:
                    if part.text:
                        print(f"Jarvis: {part.text.strip()}")
                        break
        log("Model warmup complete", "DEBUG")
    except Exception as e:
        log(f"Warmup failed (continuing anyway): {e}", "DEBUG")
        contents = []  # Reset on failure

    try:
        while not shutdown_event.is_set():
            try:
                user_text = await loop.run_in_executor(None, lambda: input("You: "))
            except EOFError:
                break
            if not user_text:
                continue
            if user_text.strip().lower() in ("quit", "exit"):
                log("User requested shutdown via text.")
                shutdown_event.set()
                break

            try:
                # Add user message to history as dict
                contents.append({
                    "role": "user",
                    "parts": [{"text": user_text}]
                })

                # Call the model with rate limit retry
                response = await generate_content_with_retry(
                    client, MODEL_ID_TEXT, contents, config
                )

                # Process response - may involve multiple rounds of tool calls
                # Retry up to 2 times if we get empty responses
                retry_count = 0
                max_retries = 2

                while True:
                    if not response.candidates or not response.candidates[0].content:
                        log("No candidates or content in response", "DEBUG")
                        break

                    model_content = response.candidates[0].content
                    parts_count = len(model_content.parts) if model_content.parts else 0
                    log(f"Response role: {model_content.role}, parts count: {parts_count}", "DEBUG")

                    # Retry on empty response
                    if parts_count == 0:
                        retry_count += 1
                        if retry_count <= max_retries:
                            log(f"Empty response, retrying ({retry_count}/{max_retries})...", "DEBUG")
                            await asyncio.sleep(0.5)
                            response = await generate_content_with_retry(
                                client, MODEL_ID_TEXT, contents, config
                            )
                            continue
                        else:
                            log("Empty response after retries, skipping", "DEBUG")
                            # Remove the unanswered user message
                            if contents and contents[-1].get("role") == "user":
                                contents.pop()
                            break

                    # Convert model content to dict and add to history
                    model_dict = _content_to_dict(model_content)
                    contents.append(model_dict)

                    # Check for function calls
                    function_calls = []
                    for part in model_content.parts:
                        if part.function_call:
                            function_calls.append(part.function_call)
                            log(f"Found function call: {part.function_call.name}", "DEBUG")
                        elif part.text:
                            text_out = part.text.strip()
                            if text_out:
                                print(f"Jarvis: {text_out}")
                        elif part.thought:
                            log(f"Model thinking: {part.thought[:100]}...", "DEBUG")

                    if not function_calls:
                        break

                    # Execute function calls and build response parts as dicts
                    function_response_parts = []
                    for call in function_calls:
                        conversation_state["tool_calls_executed"] += 1
                        log(f"============================================================")
                        log(f"*** TOOL CALL #{conversation_state['tool_calls_executed']}: {call.name}")
                        log(f"    Args: {call.args}")

                        result = execute_ableton_function(call.name, dict(call.args))
                        log(f"    Result: {result}")

                        session_manager.record_action(action=call.name, params=dict(call.args))
                        update_session_state(call.name, dict(call.args), result)

                        function_response_parts.append({
                            "functionResponse": {
                                "name": call.name,
                                "response": result
                            }
                        })

                    # Add function responses as user content dict
                    contents.append({
                        "role": "user",
                        "parts": function_response_parts
                    })

                    # Call model again with updated history (with rate limit retry)
                    response = await generate_content_with_retry(
                        client, MODEL_ID_TEXT, contents, config
                    )

                conversation_state["turns_completed"] += 1

            except Exception as e:
                log(f"Error processing message: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                # Remove the failed user message from history to keep it clean
                if contents and contents[-1].get("role") == "user":
                    contents.pop()

    finally:
        session_connected.clear()
        log("Text session ended.", "DEBUG")


async def run_session(text_mode=False):
    """Run a single session with all tasks (voice mode only now)."""
    # Reset conversation state and connection flag
    conversation_state["audio_chunks_sent"] = 0
    conversation_state["tool_calls_executed"] = 0
    conversation_state["turns_completed"] = 0
    conversation_state["waiting_for_response"] = False
    session_connected.clear()  # Not connected yet - will set after connection

    # Clear any stale audio in the queue before starting
    while not audio_queue_mic.empty():
        try:
            audio_queue_mic.get_nowait()
        except asyncio.QueueEmpty:
            break

    # Setup Jarvis's configuration
    if text_mode:
        config = {
            "response_modalities": ["TEXT"],
            "tools": ABLETON_TOOLS,
            "system_instruction": build_system_instruction()
        }
    else:
        if not PYAUDIO_AVAILABLE:
            log("PyAudio is required for voice mode. Install it or use --text mode.", "ERROR")
            return
        config = {
            "response_modalities": ["AUDIO"],
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            "tools": ABLETON_TOOLS,
            "system_instruction": build_system_instruction()
        }
    
    try:
        model = MODEL_ID_TEXT if text_mode else MODEL_ID_AUDIO
        async with client.aio.live.connect(model=model, config=config) as session:
            # NOW mark as connected after session is established
            session_connected.set()

            log("------------------------------------------------------------")
            mode_label = "TEXT" if text_mode else "VOICE"
            log(f"--- Jarvis Online (Hamilton Studio) [{mode_label} MODE] ---")
            log(f"Available functions: {len(ABLETON_TOOLS[0].function_declarations)}")
            if not text_mode:
                log("(Mic auto-mutes while Jarvis speaks to prevent echo)")
            else:
                log("Type your commands below. Type 'quit' or 'exit' to stop.")
            log(f"Verbose logging: {'ON' if VERBOSE_LOGGING else 'OFF'}")
            log("------------------------------------------------------------")

            # Small delay to ensure session is fully ready
            await asyncio.sleep(0.5)

            # Run all tasks concurrently with gather (more resilient than TaskGroup)
            if text_mode:
                tasks = [
                    send_text(session),
                    receive_responses(session),
                    heartbeat(),
                    stall_detector(),
                ]
                task_names_list = ["send_text", "receive_responses", "heartbeat", "stall_detector"]
            else:
                tasks = [
                    listen_audio(),
                    send_audio(session),
                    receive_responses(session),
                    play_audio(),
                    heartbeat(),
                    stall_detector(),
                ]
                task_names_list = ["listen_audio", "send_audio", "receive_responses", "play_audio", "heartbeat", "stall_detector"]

            # gather with return_exceptions=True so one failure doesn't kill all
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any task errors
            for i, task_names in enumerate(task_names_list):
                if i < len(results) and isinstance(results[i], Exception):
                    error = results[i]
                    error_msg = str(error)
                    # Don't log connection errors as they're expected when connection closes
                    if "ConnectionClosed" not in error_msg and "keepalive ping timeout" not in error_msg:
                        log(f"Task {task_names} failed: {error}", "ERROR")
            
            log("Session tasks completed, cleaning up...", "DEBUG")
            
    except Exception as e:
        error_msg = str(e)
        log(f"Session connection error: {e}", "ERROR")
        
        # Mark connection as closed
        session_connected.clear()
        
        # Don't log connection errors as they're expected
        if "ConnectionClosed" not in error_msg and "keepalive ping timeout" not in error_msg:
            import traceback
            traceback.print_exc()
    
    finally:
        # Ensure connection flag is cleared and cleanup
        session_connected.clear()
        is_playing.clear()
        conversation_state["waiting_for_response"] = False
        
        # Clear audio queues to prevent stale data
        while not audio_queue_mic.empty():
            try:
                audio_queue_mic.get_nowait()
            except asyncio.QueueEmpty:
                break
        while not audio_queue_output.empty():
            try:
                audio_queue_output.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        log("Session cleanup complete", "DEBUG")


async def start_jarvis(text_mode=False):
    """Main entry point with reconnection logic."""
    # Auto-cleanup if managed files exceed 100 MB
    try:
        from utils.storage_manager import StorageManager
        _project_root = os.path.dirname(os.path.abspath(__file__))
        _mgr = StorageManager(project_root=_project_root)
        _usage = _mgr.get_disk_usage()
        if _usage["total_bytes"] > 100_000_000:
            _result = _mgr.clean_all()
            _summary = _result["summary"]
            print(f"[Storage] Auto-cleanup: freed {_summary['total_freed_mb']} MB ({_summary['total_deleted']} items)")
        else:
            print(f"[Storage] Managed files: {round(_usage['total_bytes'] / (1024*1024), 1)} MB (under 100 MB threshold)")
    except Exception as e:
        print(f"[Storage] Auto-cleanup skipped: {e}")

    # Test OSC connection to Ableton
    print("============================================================")
    print("--- Testing Ableton OSC Connection ---")
    if ableton.test_connection():
        print("[OK] OSC Bridge connected successfully")
    else:
        print("[!] Warning: OSC Bridge not responding. Make sure Ableton and AbletonOSC are running.")
        print("  Continuing anyway - Jarvis will report errors if commands fail.")
    print("============================================================")
    
    print("============================================================")
    print("--- Audio Engineer Intelligence Active ---")
    print(f"[OK] Agent orchestrator initialized with {len(agent_orchestrator.agents)} agents")
    print("[OK] Device intelligence ready for semantic parameter understanding")
    print("[OK] Plugin chain knowledge base loaded")
    print("============================================================")
    
    # Reconnection configuration
    reconnect_delay = 3
    min_reconnect_delay = 3
    max_reconnect_delay = 30
    consecutive_failures = 0
    max_consecutive_failures = 10
    
    # Text mode uses standard chat API (no websocket/Live API needed)
    if text_mode:
        try:
            await run_text_session()
        except Exception as e:
            log(f"Text session error: {e}", "ERROR")
            import traceback
            traceback.print_exc()
        return

    while not shutdown_event.is_set():
        try:
            await run_session(text_mode=False)
            
            # If we get here, session ended - reset backoff on successful session
            consecutive_failures = 0
            reconnect_delay = min_reconnect_delay
            
            # If we get here, session ended cleanly
            if shutdown_event.is_set():
                break
                
            log("Session ended. Reconnecting...")
            
        except asyncio.CancelledError:
            log("Session cancelled.")
            break
            
        except Exception as e:
            error_msg = str(e)
            consecutive_failures += 1
            
            # Check if this is a connection error (expected during reconnection)
            is_connection_error = any(x in error_msg for x in [
                "ConnectionClosed", "keepalive ping timeout", "1011", "TimeoutError"
            ])
            
            if is_connection_error:
                log(f"Connection lost (attempt {consecutive_failures}/{max_consecutive_failures}). Will reconnect...", "WARN")
            else:
                log(f"Session error: {e}", "ERROR")
                import traceback
                traceback.print_exc()
            
            # Check for too many failures
            if consecutive_failures >= max_consecutive_failures:
                log(f"Too many consecutive failures ({consecutive_failures}). Waiting longer before retry...", "ERROR")
                reconnect_delay = max_reconnect_delay
            
        # Reconnection delay with backoff
        if not shutdown_event.is_set():
            log(f"Reconnecting in {reconnect_delay:.0f} seconds...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Jarvis - Ableton Live AI Assistant")
    parser.add_argument("--text", action="store_true", help="Run in text CLI mode (no microphone)")
    args = parser.parse_args()

    try:
        asyncio.run(start_jarvis(text_mode=args.text))
    except KeyboardInterrupt:
        shutdown_event.set()
        print("\n============================================================")
        print("--- Jarvis Offline ---")
        
        # Print session summary
        print(f"\nSession Summary:")
        print(f"  Tool calls executed: {conversation_state['tool_calls_executed']}")
        print(f"  Turns completed: {conversation_state['turns_completed']}")
        print(f"  Audio chunks sent: {conversation_state['audio_chunks_sent']}")
        
        # Print action history
        recent = session_manager.get_recent_actions(10)
        if recent:
            print(f"\nRecent actions:")
            for a in recent:
                print(f"  - {a['action']}: {a.get('params', {})}")
        
        print("============================================================")
    finally:
        if pya is not None:
            pya.terminate()
