"""
Tests for the Semantic Plugin Knowledge Base

Tests:
- Knowledge base loading and initialization
- Plugin and parameter info retrieval
- Semantic intent-based parameter search
- Typical range recommendations
- Parameter validation
"""

import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.plugin_kb_manager import (
    PluginKnowledgeBase,
    get_plugin_kb,
    get_plugin_info,
    get_parameter_info,
    find_parameters_for_intent,
    get_typical_range,
    validate_parameter_value
)


class TestPluginKnowledgeBase(unittest.TestCase):
    """Tests for PluginKnowledgeBase class"""
    
    @classmethod
    def setUpClass(cls):
        """Set up the knowledge base once for all tests"""
        cls.kb = get_plugin_kb()
    
    def test_kb_loaded(self):
        """Test that knowledge base loads successfully"""
        self.assertTrue(self.kb.is_loaded())
    
    def test_get_plugin_names(self):
        """Test getting list of plugin names"""
        names = self.kb.get_plugin_names()
        self.assertIsInstance(names, list)
        self.assertGreater(len(names), 0)
        
        # Check for expected plugins
        expected_plugins = ["EQ Eight", "Compressor", "Reverb", "Saturator"]
        for plugin in expected_plugins:
            self.assertIn(plugin, names, f"Expected plugin {plugin} not found")
    
    def test_all_seven_plugins_present(self):
        """Test that all 7 core plugins are documented"""
        names = self.kb.get_plugin_names()
        expected_plugins = [
            "EQ Eight",
            "Compressor", 
            "Saturator",
            "Reverb",
            "Glue Compressor",
            "Delay",
            "Multiband Dynamics"
        ]
        
        for plugin in expected_plugins:
            self.assertIn(plugin, names, f"Missing plugin: {plugin}")
    
    def test_get_plugin_info_exact_match(self):
        """Test getting plugin info with exact name"""
        info = self.kb.get_plugin_info("EQ Eight")
        self.assertIsNotNone(info)
        self.assertIn("parameters", info)
        self.assertIn("description", info)
        self.assertIn("category", info)
    
    def test_get_plugin_info_case_insensitive(self):
        """Test case-insensitive plugin lookup"""
        info = self.kb.get_plugin_info("eq eight")
        self.assertIsNotNone(info)
        
        info = self.kb.get_plugin_info("COMPRESSOR")
        self.assertIsNotNone(info)
    
    def test_get_plugin_info_partial_match(self):
        """Test partial name matching"""
        info = self.kb.get_plugin_info("Glue")
        self.assertIsNotNone(info)
        self.assertEqual(info.get("category"), "compressor")
    
    def test_get_plugin_info_nonexistent(self):
        """Test handling of nonexistent plugin"""
        info = self.kb.get_plugin_info("Nonexistent Plugin XYZ")
        self.assertIsNone(info)
    
    def test_get_parameter_info(self):
        """Test getting parameter info"""
        param_info = self.kb.get_parameter_info("EQ Eight", "1 Frequency A")
        self.assertIsNotNone(param_info)
        self.assertIn("description", param_info)
        self.assertIn("min", param_info)
        self.assertIn("max", param_info)
    
    def test_get_parameter_info_partial_match(self):
        """Test partial parameter name matching"""
        param_info = self.kb.get_parameter_info("EQ Eight", "Frequency")
        self.assertIsNotNone(param_info)
    
    def test_plugins_have_complete_metadata(self):
        """Test that all plugins have complete metadata"""
        for plugin_name in self.kb.get_plugin_names():
            with self.subTest(plugin=plugin_name):
                info = self.kb.get_plugin_info(plugin_name)
                self.assertIsNotNone(info)
                
                # Check required fields
                self.assertIn("description", info)
                self.assertIn("category", info)
                self.assertIn("parameters", info)
                
                # Check parameters have required fields
                params = info.get("parameters", {})
                self.assertGreater(len(params), 0, f"{plugin_name} has no parameters")
                
                for param_name, param_info in params.items():
                    self.assertIn("description", param_info, 
                                  f"{plugin_name}.{param_name} missing description")
                    self.assertIn("min", param_info,
                                  f"{plugin_name}.{param_name} missing min")
                    self.assertIn("max", param_info,
                                  f"{plugin_name}.{param_name} missing max")


class TestSemanticSearch(unittest.TestCase):
    """Tests for semantic intent-based parameter search"""
    
    @classmethod
    def setUpClass(cls):
        cls.kb = get_plugin_kb()
    
    def test_find_parameters_for_intent_gain(self):
        """Test finding gain-related parameters"""
        matches = self.kb.find_parameters_for_intent("EQ Eight", "gain")
        self.assertGreater(len(matches), 0)
        
        # Should find gain parameters
        param_names = [m["name"] for m in matches]
        self.assertTrue(any("Gain" in name for name in param_names))
    
    def test_find_parameters_for_intent_threshold(self):
        """Test finding threshold-related parameters"""
        matches = self.kb.find_parameters_for_intent("Compressor", "threshold")
        self.assertGreater(len(matches), 0)
        
        # Should have Threshold as top match
        self.assertEqual(matches[0]["name"], "Threshold")
    
    def test_find_parameters_for_intent_mud(self):
        """Test finding parameters for 'cut_mud' intent"""
        matches = self.kb.find_parameters_for_intent("EQ Eight", "mud")
        self.assertGreater(len(matches), 0)
        
        # Should find frequency and gain parameters
        param_names = [m["name"] for m in matches]
        self.assertTrue(any("Frequency" in name or "Gain" in name for name in param_names))
    
    def test_find_parameters_for_intent_warmth(self):
        """Test finding parameters for warmth/saturation"""
        matches = self.kb.find_parameters_for_intent("Saturator", "warmth")
        # Should find relevant parameters
        self.assertIsInstance(matches, list)
    
    def test_find_parameters_scores_sorted(self):
        """Test that results are sorted by relevance score"""
        matches = self.kb.find_parameters_for_intent("Compressor", "attack")
        
        if len(matches) > 1:
            scores = [m["score"] for m in matches]
            self.assertEqual(scores, sorted(scores, reverse=True))


class TestTypicalRanges(unittest.TestCase):
    """Tests for typical range recommendations"""
    
    @classmethod
    def setUpClass(cls):
        cls.kb = get_plugin_kb()
    
    def test_get_typical_range_exact(self):
        """Test getting typical range with exact use case"""
        range_info = self.kb.get_typical_range("EQ Eight", "1 Frequency A", "vocal_high_pass")
        self.assertIsNotNone(range_info)
        self.assertIn("min", range_info)
        self.assertIn("max", range_info)
    
    def test_get_typical_range_partial(self):
        """Test getting typical range with partial match"""
        range_info = self.kb.get_typical_range("Compressor", "Threshold", "aggressive")
        self.assertIsNotNone(range_info)
    
    def test_typical_ranges_within_limits(self):
        """Test that typical ranges are within parameter limits"""
        param_info = self.kb.get_parameter_info("EQ Eight", "1 Gain A")
        if param_info and "typical_ranges" in param_info:
            min_val = param_info["min"]
            max_val = param_info["max"]
            
            for use_case, range_info in param_info["typical_ranges"].items():
                with self.subTest(use_case=use_case):
                    if "min" in range_info:
                        self.assertGreaterEqual(range_info["min"], min_val)
                    if "max" in range_info:
                        self.assertLessEqual(range_info["max"], max_val)


class TestParameterValidation(unittest.TestCase):
    """Tests for parameter value validation"""
    
    @classmethod
    def setUpClass(cls):
        cls.kb = get_plugin_kb()
    
    def test_validate_within_range(self):
        """Test validation of value within range"""
        is_valid, value, msg = self.kb.validate_parameter_value(
            "EQ Eight", "1 Gain A", 5.0
        )
        self.assertTrue(is_valid)
        self.assertEqual(value, 5.0)
    
    def test_validate_below_min(self):
        """Test validation of value below minimum"""
        is_valid, value, msg = self.kb.validate_parameter_value(
            "EQ Eight", "1 Gain A", -50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(value, -15.0)  # Clamped to min
    
    def test_validate_above_max(self):
        """Test validation of value above maximum"""
        is_valid, value, msg = self.kb.validate_parameter_value(
            "EQ Eight", "1 Gain A", 50.0
        )
        self.assertFalse(is_valid)
        self.assertEqual(value, 15.0)  # Clamped to max
    
    def test_validate_unknown_parameter(self):
        """Test validation of unknown parameter"""
        is_valid, value, msg = self.kb.validate_parameter_value(
            "EQ Eight", "Unknown Parameter", 5.0
        )
        # Should return true for unknown parameters
        self.assertTrue(is_valid)
        self.assertEqual(value, 5.0)


class TestIntentRecommendations(unittest.TestCase):
    """Tests for semantic intent recommendations"""
    
    @classmethod
    def setUpClass(cls):
        cls.kb = get_plugin_kb()
    
    def test_get_intent_recommendation(self):
        """Test getting recommendation for an intent"""
        rec = self.kb.get_intent_recommendation("cut_mud")
        self.assertIsNotNone(rec)
        self.assertIn("suggested_plugin", rec)
    
    def test_get_intent_recommendation_partial(self):
        """Test partial intent matching"""
        rec = self.kb.get_intent_recommendation("add_warmth")
        self.assertIsNotNone(rec)
    
    def test_get_signal_flow_recommendation(self):
        """Test getting signal flow recommendation"""
        flow = self.kb.get_signal_flow_recommendation("standard_vocal_chain")
        self.assertIsInstance(flow, list)
        self.assertGreater(len(flow), 0)
        
        # Check structure
        for item in flow:
            self.assertIn("plugin", item)
            self.assertIn("purpose", item)
    
    def test_get_common_vocal_settings(self):
        """Test getting common vocal settings"""
        settings = self.kb.get_common_vocal_settings("Compressor")
        self.assertIsNotNone(settings)


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for module-level convenience functions"""
    
    def test_get_plugin_info_function(self):
        """Test module-level get_plugin_info"""
        info = get_plugin_info("Reverb")
        self.assertIsNotNone(info)
    
    def test_get_parameter_info_function(self):
        """Test module-level get_parameter_info"""
        info = get_parameter_info("Reverb", "Decay Time")
        self.assertIsNotNone(info)
    
    def test_find_parameters_for_intent_function(self):
        """Test module-level find_parameters_for_intent"""
        matches = find_parameters_for_intent("Delay", "feedback")
        self.assertIsInstance(matches, list)
    
    def test_validate_parameter_value_function(self):
        """Test module-level validate_parameter_value"""
        is_valid, value, msg = validate_parameter_value("Compressor", "Ratio", 4.0)
        self.assertTrue(is_valid)


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)

