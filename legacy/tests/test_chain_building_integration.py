"""
Integration Chain Building Test

Tests the full stack including:
- PluginChainBuilder for chain building
- VST discovery and plugin matching
- Plugin loading via Remote Script
- Parameter configuration via ReliableParameterController

Run with: python tests/test_chain_building_integration.py
"""

import asyncio
import os
import sys
import time
import argparse
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.chain_test_utils import (
    ChainTestResult,
    DeviceResult,
    ParameterResult,
    print_chain_report,
    print_summary,
    save_test_results,
    create_reliable_controller,
    get_device_count,
    clear_track_devices,
)

from plugins.chain_builder import PluginChainBuilder, PluginChain
from discovery.vst_discovery import get_vst_discovery, VSTDiscoveryService
from knowledge.plugin_chain_kb import get_plugin_chain_kb


class IntegrationTestResult:
    """Result for integration tests with additional metadata"""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = False
        self.message = ""
        self.details: Dict[str, Any] = {}
        self.execution_time = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "execution_time": self.execution_time
        }


def test_vst_discovery_connection() -> IntegrationTestResult:
    """Test that VST discovery service can connect to Ableton"""
    result = IntegrationTestResult("VST Discovery Connection")
    start = time.time()
    
    print("\n🔌 Testing VST Discovery Connection...")
    
    try:
        discovery = get_vst_discovery()
        
        # Check if we have cached plugins
        plugins = discovery.get_all_plugins()
        
        if plugins:
            result.passed = True
            result.message = f"Found {len(plugins)} cached plugins"
            result.details["plugin_count"] = len(plugins)
            result.details["categories"] = discovery.get_categories()
            print(f"   ✅ Found {len(plugins)} plugins in cache")
            print(f"   📂 Categories: {', '.join(discovery.get_categories()[:5])}...")
        else:
            # Try to refresh from Ableton
            print("   ⏳ No cache, attempting refresh from Ableton...")
            if discovery.refresh_plugins():
                plugins = discovery.get_all_plugins()
                result.passed = True
                result.message = f"Refreshed and found {len(plugins)} plugins"
                result.details["plugin_count"] = len(plugins)
            else:
                result.message = "Could not connect to Ableton for plugin refresh"
                print("   ❌ Could not refresh plugins from Ableton")
    except Exception as e:
        result.message = f"Error: {e}"
        print(f"   ❌ Error: {e}")
    
    result.execution_time = time.time() - start
    return result


def test_plugin_matching() -> IntegrationTestResult:
    """Test plugin matching with exact and fuzzy matches"""
    result = IntegrationTestResult("Plugin Matching")
    start = time.time()
    
    print("\n🔍 Testing Plugin Matching...")
    
    try:
        builder = PluginChainBuilder()
        
        # Test cases: (query, expected_type)
        test_cases = [
            ("EQ Eight", "eq"),
            ("Compressor", "compressor"),
            ("Reverb", "reverb"),
            ("Saturator", "saturation"),
            ("Glue Compressor", "compressor"),
            ("Multiband Dynamics", "dynamics"),
            ("Delay", "delay"),
            ("Limiter", "limiter"),
        ]
        
        matches = []
        failures = []
        
        for query, expected_type in test_cases:
            # Try to find the plugin
            matched, is_alternative, confidence = builder._match_plugin(
                desired_name=query,
                plugin_type=expected_type
            )
            
            if matched:
                matches.append({
                    "query": query,
                    "matched": matched.name,
                    "confidence": confidence,
                    "is_alternative": is_alternative
                })
                status = "✅" if confidence > 0.7 else "⚠️"
                alt = " (alt)" if is_alternative else ""
                print(f"   {status} '{query}' → '{matched.name}'{alt} ({confidence:.2f})")
            else:
                failures.append(query)
                print(f"   ❌ '{query}' → No match found")
        
        result.details["matches"] = matches
        result.details["failures"] = failures
        result.details["match_rate"] = len(matches) / len(test_cases) if test_cases else 0
        
        if len(matches) >= len(test_cases) * 0.9:  # 90%+ match rate
            result.passed = True
            result.message = f"Matched {len(matches)}/{len(test_cases)} plugins"
        else:
            result.message = f"Low match rate: {len(matches)}/{len(test_cases)}"
        
    except Exception as e:
        result.message = f"Error: {e}"
        print(f"   ❌ Error: {e}")
    
    result.execution_time = time.time() - start
    return result


def test_chain_validation() -> IntegrationTestResult:
    """Test chain validation logic"""
    result = IntegrationTestResult("Chain Validation")
    start = time.time()
    
    print("\n✅ Testing Chain Validation...")
    
    try:
        builder = PluginChainBuilder()
        
        # Build a preset chain
        chain = builder.get_preset_chain("basic", "vocal")
        
        print(f"   Built chain: {chain.name} with {len(chain.slots)} slots")
        
        # Validate the chain
        validation = builder.validate_chain(chain)
        
        result.details["chain_name"] = chain.name
        result.details["slot_count"] = len(chain.slots)
        result.details["validation"] = validation
        
        print(f"   Valid: {validation['valid']}")
        print(f"   Issues: {len(validation['issues'])}")
        print(f"   Warnings: {len(validation['warnings'])}")
        
        if validation["valid"]:
            result.passed = True
            result.message = f"Chain validated successfully"
            
            # Show matched plugins
            for i, slot in enumerate(chain.slots):
                if slot.matched_plugin:
                    print(f"      {i+1}. {slot.plugin_type} → {slot.matched_plugin.name}")
        else:
            result.message = f"Validation failed: {len(validation['issues'])} issues"
            for issue in validation["issues"]:
                print(f"      ❌ {issue}")
        
        if validation["warnings"]:
            print("   Warnings:")
            for warn in validation["warnings"]:
                print(f"      ⚠️ {warn}")
        
    except Exception as e:
        result.message = f"Error: {e}"
        print(f"   ❌ Error: {e}")
    
    result.execution_time = time.time() - start
    return result


def test_preset_chain_building() -> IntegrationTestResult:
    """Test building chains from presets"""
    result = IntegrationTestResult("Preset Chain Building")
    start = time.time()
    
    print("\n🎛️ Testing Preset Chain Building...")
    
    try:
        builder = PluginChainBuilder()
        
        # Test multiple presets
        presets = [
            ("basic", "vocal"),
            ("full", "vocal"),
            ("bus", "drum"),
        ]
        
        built_chains = []
        failures = []
        
        for preset_name, track_type in presets:
            try:
                chain = builder.get_preset_chain(preset_name, track_type)
                
                if chain and len(chain.slots) > 0:
                    built_chains.append({
                        "preset": preset_name,
                        "track_type": track_type,
                        "slot_count": len(chain.slots),
                        "confidence": chain.confidence
                    })
                    print(f"   ✅ {preset_name}_{track_type}: {len(chain.slots)} plugins")
                else:
                    failures.append(f"{preset_name}_{track_type}")
                    print(f"   ❌ {preset_name}_{track_type}: Empty or null chain")
            except Exception as e:
                failures.append(f"{preset_name}_{track_type}: {e}")
                print(f"   ❌ {preset_name}_{track_type}: {e}")
        
        result.details["built_chains"] = built_chains
        result.details["failures"] = failures
        
        if len(built_chains) >= len(presets) * 0.8:
            result.passed = True
            result.message = f"Built {len(built_chains)}/{len(presets)} preset chains"
        else:
            result.message = f"Failed to build {len(failures)} chains"
        
    except Exception as e:
        result.message = f"Error: {e}"
        print(f"   ❌ Error: {e}")
    
    result.execution_time = time.time() - start
    return result


def test_chain_from_research_data() -> IntegrationTestResult:
    """Test building chain from simulated research results"""
    result = IntegrationTestResult("Chain From Research Data")
    start = time.time()
    
    print("\n📚 Testing Chain Building from Research Data...")
    
    try:
        builder = PluginChainBuilder()
        
        # Simulated research result (as if from ResearchAgent)
        research_result = {
            "artist_or_style": "Test Artist",
            "track_type": "vocal",
            "confidence": 0.85,
            "chain": [
                {
                    "type": "eq",
                    "purpose": "high_pass",
                    "plugin_name": "EQ Eight",
                    "settings": {"high_pass_freq": "100Hz"}
                },
                {
                    "type": "compressor",
                    "purpose": "dynamics",
                    "plugin_name": "Compressor",
                    "settings": {"ratio": "4:1", "attack": "fast"}
                },
                {
                    "type": "de-esser",
                    "purpose": "sibilance",
                    "plugin_name": "Multiband Dynamics",
                    "settings": {}
                },
                {
                    "type": "reverb",
                    "purpose": "space",
                    "plugin_name": "Reverb",
                    "settings": {"decay": "medium"}
                },
            ]
        }
        
        chain = builder.build_chain_from_research(research_result)
        
        print(f"   Chain name: {chain.name}")
        print(f"   Slots: {len(chain.slots)}")
        print(f"   Confidence: {chain.confidence:.2f}")
        
        matched_count = sum(1 for s in chain.slots if s.matched_plugin)
        print(f"   Matched plugins: {matched_count}/{len(chain.slots)}")
        
        for i, slot in enumerate(chain.slots):
            if slot.matched_plugin:
                alt = " (alt)" if slot.is_alternative else ""
                print(f"      {i+1}. {slot.plugin_type} → {slot.matched_plugin.name}{alt}")
            else:
                print(f"      {i+1}. {slot.plugin_type} → ❌ No match")
        
        result.details["chain_name"] = chain.name
        result.details["slot_count"] = len(chain.slots)
        result.details["matched_count"] = matched_count
        result.details["confidence"] = chain.confidence
        
        if matched_count == len(chain.slots):
            result.passed = True
            result.message = f"All {matched_count} plugins matched successfully"
        elif matched_count >= len(chain.slots) * 0.8:
            result.passed = True
            result.message = f"Matched {matched_count}/{len(chain.slots)} plugins (acceptable)"
        else:
            result.message = f"Low match rate: {matched_count}/{len(chain.slots)}"
        
    except Exception as e:
        result.message = f"Error: {e}"
        import traceback
        print(f"   ❌ Error: {e}")
        traceback.print_exc()
    
    result.execution_time = time.time() - start
    return result


def test_knowledge_base_lookup() -> IntegrationTestResult:
    """Test plugin chain knowledge base lookup"""
    result = IntegrationTestResult("Knowledge Base Lookup")
    start = time.time()
    
    print("\n📖 Testing Knowledge Base Lookup...")
    
    try:
        kb = get_plugin_chain_kb()
        
        # List available chains
        chains = kb.list_chains()
        print(f"   Found {len(chains)} chains in knowledge base")
        
        # Try to get specific chains
        test_lookups = [
            ("Billie Eilish", "vocal"),
            ("The Weeknd", "vocal"),
            ("modern pop", "vocal"),
        ]
        
        found = []
        not_found = []
        
        for artist, track_type in test_lookups:
            chain_data = kb.get_chain_for_research(artist, track_type)
            
            if chain_data:
                found.append({
                    "artist": artist,
                    "track_type": track_type,
                    "plugin_count": len(chain_data.get("chain", []))
                })
                print(f"   ✅ '{artist}' ({track_type}): {len(chain_data.get('chain', []))} plugins")
            else:
                not_found.append(f"{artist}_{track_type}")
                print(f"   ❌ '{artist}' ({track_type}): Not found")
        
        result.details["total_chains"] = len(chains)
        result.details["found"] = found
        result.details["not_found"] = not_found
        
        if len(found) >= len(test_lookups) * 0.5:
            result.passed = True
            result.message = f"Found {len(found)}/{len(test_lookups)} chains"
        else:
            result.message = f"Only found {len(found)}/{len(test_lookups)} chains"
        
    except Exception as e:
        result.message = f"Error: {e}"
        print(f"   ❌ Error: {e}")
    
    result.execution_time = time.time() - start
    return result


async def test_full_workflow(track_index: int = 0) -> ChainTestResult:
    """
    Test complete workflow: build → validate → load → configure
    
    This is the full integration test that validates the entire stack.
    """
    print("\n" + "=" * 60)
    print("🔄 FULL WORKFLOW TEST")
    print("   Build → Validate → Load → Configure")
    print("=" * 60)
    
    chain_result = ChainTestResult(
        chain_name="full_workflow_integration",
        track_index=track_index
    )
    
    reliable = create_reliable_controller(verbose=True)
    builder = PluginChainBuilder()
    
    try:
        # Step 1: Build chain from preset
        print("\n📋 Step 1: Building chain from preset...")
        chain = builder.get_preset_chain("basic", "vocal")
        
        if not chain or len(chain.slots) == 0:
            print("   ❌ Failed to build chain")
            chain_result.finish()
            return chain_result
        
        print(f"   ✅ Built chain with {len(chain.slots)} slots")
        
        # Step 2: Validate chain
        print("\n✅ Step 2: Validating chain...")
        validation = builder.validate_chain(chain)
        
        if not validation["valid"]:
            print(f"   ❌ Chain validation failed: {validation['issues']}")
            chain_result.finish()
            return chain_result
        
        print(f"   ✅ Chain validated (confidence: {chain.confidence:.2f})")
        
        # Step 3: Clear track
        print(f"\n🧹 Step 3: Clearing track {track_index}...")
        clear_track_devices(track_index, reliable)
        
        # Step 4: Load chain
        print("\n📦 Step 4: Loading chain onto track...")
        load_result = await builder.load_chain_on_track(chain, track_index)
        
        print(f"   Loaded: {len(load_result.get('plugins_loaded', []))}")
        print(f"   Failed: {len(load_result.get('plugins_failed', []))}")
        
        # Step 5: Configure parameters with ReliableParameterController
        print("\n🎛️ Step 5: Configuring parameters...")
        
        for i, slot in enumerate(chain.slots):
            device_name = slot.matched_plugin.name if slot.matched_plugin else "Unknown"
            
            device_result = DeviceResult(
                device_name=device_name,
                device_type=slot.plugin_type,
                device_index=i,
                load_success=True,  # Assume loaded if we got here
                load_message="Loaded via PluginChainBuilder",
                ready=False
            )
            
            # Check if device is ready
            device_result.ready = reliable.wait_for_device_ready(
                track_index, i, timeout=3.0
            )
            
            if not device_result.ready:
                print(f"   ⚠️ Device {i} ({device_name}) not ready")
                chain_result.device_results.append(device_result)
                continue
            
            # Try to set some parameters from slot.settings
            if slot.settings:
                for param_name, value in slot.settings.items():
                    # Settings in chains are often strings like "80Hz"
                    # Try to extract numeric value
                    try:
                        if isinstance(value, str):
                            # Extract numbers from strings like "80Hz", "4:1", etc.
                            import re
                            numbers = re.findall(r'[\d.]+', value)
                            if numbers:
                                numeric_value = float(numbers[0])
                            else:
                                continue  # Skip non-numeric settings
                        else:
                            numeric_value = float(value)
                        
                        param_result = reliable.set_parameter_by_name(
                            track_index, i, param_name, numeric_value
                        )
                        
                        pr = ParameterResult(
                            param_name=param_name,
                            param_index=param_result.get("param_index"),
                            requested_value=numeric_value,
                            actual_value=param_result.get("actual_value"),
                            success=param_result.get("success", False),
                            verified=param_result.get("verified", False),
                            message=param_result.get("message", ""),
                            attempts=param_result.get("attempts", 1)
                        )
                        device_result.param_results.append(pr)
                        
                    except (ValueError, TypeError) as e:
                        # Skip non-numeric or problematic settings
                        continue
            
            chain_result.device_results.append(device_result)
        
        # Step 6: Verify final state
        print("\n🔍 Step 6: Verifying final state...")
        final_device_count = get_device_count(track_index)
        print(f"   Devices on track: {final_device_count}")
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
    
    chain_result.finish()
    print_chain_report(chain_result)
    
    return chain_result


def run_all_integration_tests(track_index: int = 0) -> List[IntegrationTestResult]:
    """Run all integration tests"""
    print("\n" + "=" * 60)
    print("🎬 STARTING INTEGRATION CHAIN BUILDING TESTS")
    print("=" * 60)
    
    results = []
    
    # Unit-level integration tests (no Ableton needed)
    print("\n📋 Phase 1: Unit Integration Tests")
    
    results.append(test_vst_discovery_connection())
    results.append(test_plugin_matching())
    results.append(test_chain_validation())
    results.append(test_preset_chain_building())
    results.append(test_chain_from_research_data())
    results.append(test_knowledge_base_lookup())
    
    # Print phase 1 summary
    phase1_passed = sum(1 for r in results if r.passed)
    print(f"\n📊 Phase 1 Results: {phase1_passed}/{len(results)} passed")
    
    return results


async def run_full_integration_test(track_index: int = 0) -> Dict[str, Any]:
    """Run full workflow integration test (requires Ableton)"""
    print("\n" + "=" * 60)
    print("🎬 FULL INTEGRATION TEST WITH ABLETON")
    print("=" * 60)
    
    # Run unit tests first
    unit_results = run_all_integration_tests(track_index)
    
    # Run full workflow test
    print("\n📋 Phase 2: Full Workflow Test (requires Ableton)")
    workflow_result = await test_full_workflow(track_index)
    
    # Combine results
    combined = {
        "unit_tests": [r.to_dict() for r in unit_results],
        "unit_passed": sum(1 for r in unit_results if r.passed),
        "unit_total": len(unit_results),
        "workflow_result": workflow_result.to_dict(),
        "workflow_passed": workflow_result.overall_success,
        "overall_passed": (
            sum(1 for r in unit_results if r.passed) >= len(unit_results) * 0.8
            and workflow_result.overall_success
        )
    }
    
    # Print overall summary
    print("\n" + "=" * 60)
    print("📊 INTEGRATION TEST SUMMARY")
    print("=" * 60)
    
    print(f"\nUnit Tests: {combined['unit_passed']}/{combined['unit_total']} passed")
    print(f"Workflow Test: {'✅ PASSED' if combined['workflow_passed'] else '❌ FAILED'}")
    print(f"Overall: {'✅ PASSED' if combined['overall_passed'] else '❌ FAILED'}")
    
    # Per-test results
    print("\nUnit Test Details:")
    for r in unit_results:
        status = "✅" if r.passed else "❌"
        print(f"   {status} {r.test_name}: {r.message}")
    
    print("\n" + "=" * 60)
    
    return combined


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Integration Chain Building Tests")
    parser.add_argument("--track", type=int, default=0,
                        help="Track index to test on (0-based, default: 0)")
    parser.add_argument("--unit-only", action="store_true",
                        help="Run only unit tests (no Ableton required)")
    parser.add_argument("--workflow-only", action="store_true",
                        help="Run only the full workflow test")
    
    args = parser.parse_args()
    
    print("\n🔗 Integration Chain Building Test Suite")
    print(f"   Target Track: {args.track} (Track {args.track + 1} in Ableton)")
    
    if args.unit_only:
        results = run_all_integration_tests(args.track)
        passed = sum(1 for r in results if r.passed)
        print(f"\n📊 Final: {passed}/{len(results)} unit tests passed")
    elif args.workflow_only:
        asyncio.run(test_full_workflow(args.track))
    else:
        asyncio.run(run_full_integration_test(args.track))

