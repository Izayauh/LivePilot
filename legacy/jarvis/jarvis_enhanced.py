"""
Jarvis Enhanced - AI Audio Engineer with Multi-Agent System

This is the enhanced version of Jarvis that includes:
- Multi-agent orchestration
- Audio engineering knowledge
- Research capabilities
- Self-learning system
- Dynamic tool discovery

For basic voice control, use jarvis_engine.py instead.
"""

import asyncio
import os
import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Core components
from ableton_controls import ableton
from jarvis_tools import ABLETON_TOOLS

# Multi-agent system
from agent_system import orchestrator, AgentOrchestrator
from agents.router_agent import RouterAgent
from agents.executor_agent import ExecutorAgent
from agents.audio_engineer_agent import AudioEngineerAgent
from agents.research_agent import ResearchAgent
from agents.planner_agent import PlannerAgent
from agents.implementation_agent import ImplementationAgent

# Knowledge and learning
from knowledge.audio_kb import audio_kb
from discovery.tool_registry import tool_registry
from discovery.learning_system import learning_system

# Setup
load_dotenv()
os.environ["PYTHONIOENCODING"] = "utf-8"

# API Configuration
API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
MODEL_ID = "gemini-2.0-flash-exp"

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512

audio = pyaudio.PyAudio()

# Setup Playback Stream
playback_stream = audio.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    output=True
)


def initialize_agents():
    """Initialize and register all agents with the orchestrator"""
    print("--- Initializing Multi-Agent System ---")
    
    # Set core components
    orchestrator.set_gemini_client(client)
    orchestrator.set_ableton_controller(ableton)
    
    # Register agents
    orchestrator.register_agent(RouterAgent(orchestrator))
    orchestrator.register_agent(ExecutorAgent(orchestrator))
    orchestrator.register_agent(AudioEngineerAgent(orchestrator))
    orchestrator.register_agent(ResearchAgent(orchestrator))
    orchestrator.register_agent(PlannerAgent(orchestrator))
    orchestrator.register_agent(ImplementationAgent(orchestrator))
    
    print(f"✓ Registered {len(orchestrator.get_registered_agents())} agents")
    print(f"✓ Loaded {len(audio_kb.techniques)} production techniques")
    print(f"✓ Loaded {len(tool_registry.get_all_tools())} tools")
    
    # Show learning summary
    summary = learning_system.get_learning_summary()
    print(f"✓ Learning system: {summary['total_actions']} actions tracked")


async def send_mic_audio(session):
    """Stream microphone audio to Gemini"""
    input_stream = audio.open(
        format=FORMAT, 
        channels=CHANNELS,
        rate=RATE, 
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print(">>> Jarvis Enhanced is listening...")
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=f'audio/pcm;rate={RATE}')
            )
            await asyncio.sleep(0)
    except Exception as e:
        print(f"Mic Error: {e}")
    finally:
        input_stream.stop_stream()
        input_stream.close()


async def handle_responses(session):
    """Handle AI responses with enhanced multi-agent processing"""
    try:
        async for response in session.receive():
            # Handle voice output
            if response.data:
                playback_stream.write(response.data)
            
            # Handle text output
            if response.text:
                print(f"Jarvis: {response.text}")
            
            # Handle tool calls with enhanced execution
            if response.tool_call and response.tool_call.function_calls:
                for call in response.tool_call.function_calls:
                    print(f"*** Processing: {call.name}")
                    
                    # Execute through enhanced system
                    result = await execute_enhanced(call.name, call.args)
                    
                    # Track in learning system
                    learning_system.record_action(
                        action=call.name,
                        success=result.get("success", False),
                        context={"args": call.args}
                    )
                    
                    # Track in tool registry
                    if result.get("success"):
                        tool_registry.record_success(call.name)
                    else:
                        tool_registry.record_failure(call.name)
                    
                    # Send result back to Gemini
                    await session.send_tool_response(
                        types.LiveClientToolResponse(
                            function_responses=[
                                types.FunctionResponse(
                                    id=call.id,
                                    name=call.name,
                                    response=result
                                )
                            ]
                        )
                    )
                    
                    # Print result
                    if result.get("success"):
                        print(f"✓ {result.get('message')}")
                    else:
                        print(f"✗ {result.get('message')}")
                        
                        # Check for alternatives
                        alt = learning_system.should_suggest_alternative(call.name)
                        if alt:
                            print(f"  💡 Suggestion: Try '{alt}' instead")
                
    except Exception as e:
        print(f"Session Error: {e}")


async def execute_enhanced(function_name: str, args: dict) -> dict:
    """
    Enhanced execution that can handle complex workflows
    """
    # First, try direct execution for simple commands
    result = execute_ableton_function(function_name, args)
    
    if result.get("success"):
        return result
    
    # If direct execution failed, try through the agent system
    # This allows for more complex handling
    try:
        from agents import AgentType
        
        if AgentType.EXECUTOR in orchestrator.agents:
            executor_result = await orchestrator.process_user_request(
                f"Execute {function_name} with {args}"
            )
            return {
                "success": executor_result.success,
                "message": executor_result.message,
                "data": executor_result.data
            }
    except Exception as e:
        return {"success": False, "message": f"Enhanced execution error: {e}"}
    
    return result


def execute_ableton_function(function_name: str, args: dict) -> dict:
    """Execute a basic Ableton control function"""
    try:
        function_map = {
            # Playback
            "play": lambda: ableton.play(),
            "stop": lambda: ableton.stop(),
            "continue_playback": lambda: ableton.continue_playback(),
            "start_recording": lambda: ableton.start_recording(),
            "stop_recording": lambda: ableton.stop_recording(),
            "toggle_metronome": lambda: ableton.toggle_metronome(args.get("state")),
            
            # Transport
            "set_tempo": lambda: ableton.set_tempo(args.get("bpm")),
            "set_position": lambda: ableton.set_position(args.get("beat")),
            "set_loop": lambda: ableton.set_loop(args.get("enabled")),
            "set_loop_start": lambda: ableton.set_loop_start(args.get("beat")),
            "set_loop_length": lambda: ableton.set_loop_length(args.get("beats")),
            
            # Track controls
            "mute_track": lambda: ableton.mute_track(args.get("track_index"), args.get("muted")),
            "solo_track": lambda: ableton.solo_track(args.get("track_index"), args.get("soloed")),
            "arm_track": lambda: ableton.arm_track(args.get("track_index"), args.get("armed")),
            "set_track_volume": lambda: ableton.set_track_volume(args.get("track_index"), args.get("volume")),
            "set_track_pan": lambda: ableton.set_track_pan(args.get("track_index"), args.get("pan")),
            "set_track_send": lambda: ableton.set_track_send(args.get("track_index"), args.get("send_index"), args.get("level")),
            
            # Scene/Clip
            "fire_scene": lambda: ableton.fire_scene(args.get("scene_index")),
            "fire_clip": lambda: ableton.fire_clip(args.get("track_index"), args.get("clip_index")),
            "stop_clip": lambda: ableton.stop_clip(args.get("track_index")),
            "stop_all_clips": lambda: ableton.stop_all_clips(),
        }
        
        if function_name in function_map:
            return function_map[function_name]()
        else:
            return {"success": False, "message": f"Unknown function: {function_name}"}
            
    except Exception as e:
        return {"success": False, "message": f"Execution error: {e}"}


def build_system_instruction() -> str:
    """Build enhanced system instruction with knowledge base context"""
    techniques = audio_kb.get_technique("parallel_compression")
    genres = list(audio_kb.genres.keys())
    
    return f"""You are Jarvis, an advanced AI audio engineer and studio assistant for a music producer in Hamilton, Ohio.

You control Ableton Live 11 through voice commands and have deep knowledge of professional audio engineering.

## Core Capabilities:
1. **Direct Ableton Control**: Play, stop, mute, solo, arm tracks, set tempo, fire scenes/clips
2. **Production Knowledge**: You understand mixing, mastering, effects, and production techniques
3. **Genre Expertise**: You know the conventions for {', '.join(genres)}
4. **Workflow Optimization**: You can suggest efficient approaches to production tasks

## Track Indexing:
CRITICAL: Track indices are 0-based. When the user says 'Track 1', use track_index=0.
Track 2 = index 1, Track 3 = index 2, and so on. Same for scenes and clips.

## Production Techniques You Know:
- Parallel compression for punch and impact
- Sidechain compression for clarity and pumping
- EQ techniques (subtractive, high-pass, presence, air)
- Reverb and spatial processing
- Drum bus processing
- Vocal chains

## Response Style:
- Be concise and professional
- Confirm actions after executing
- Suggest improvements when appropriate
- Explain techniques if asked

Always prioritize the user's creative vision while offering professional guidance."""


async def start_jarvis_enhanced():
    """Start the enhanced Jarvis system"""
    print("\n" + "="*60)
    print("  JARVIS ENHANCED - AI AUDIO ENGINEER")
    print("="*60 + "\n")
    
    # Initialize agent system
    initialize_agents()
    
    # Test OSC connection
    print("\n--- Testing Ableton OSC Connection ---")
    if ableton.test_connection():
        print("✓ OSC Bridge connected successfully")
    else:
        print("⚠ Warning: OSC Bridge not responding")
        print("  Make sure Ableton and AbletonOSC are running.")
    
    # Build config
    config = {
        "response_modalities": ["audio", "text"],
        "speech_config": types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        "tools": ABLETON_TOOLS,
        "system_instruction": build_system_instruction()
    }
    
    print("\n--- Jarvis Enhanced Online ---")
    print(f"Available functions: {len(ABLETON_TOOLS[0].function_declarations)}")
    print(f"Agents active: {orchestrator.get_registered_agents()}")
    print("\n" + "="*60 + "\n")
    
    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        await asyncio.gather(
            send_mic_audio(session), 
            handle_responses(session)
        )


def main():
    """Main entry point"""
    try:
        asyncio.run(start_jarvis_enhanced())
    except KeyboardInterrupt:
        print("\n\n--- Jarvis Enhanced Offline ---")
        
        # Print learning summary
        summary = learning_system.get_learning_summary()
        print(f"\nSession Summary:")
        print(f"  Actions executed: {summary['total_actions']}")
        print(f"  Success rate: {summary['overall_success_rate']:.1%}")
        print(f"  Corrections made: {summary['total_corrections']}")
        
    finally:
        playback_stream.stop_stream()
        playback_stream.close()
        audio.terminate()


if __name__ == "__main__":
    main()

