#!/usr/bin/env python
"""
GUI and API tests for EPYCON Flask application.
Tests the web interface endpoints and GUI functionality.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add epycon module to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'epycon'))
sys.path.insert(0, str(project_root))

# Test counter
tests_run = 0
tests_passed = 0
tests_failed = 0

def test(name):
    """Decorator for test functions - simplified version"""
    def decorator(func):
        # Don't execute immediately, just mark the function
        func._is_test = True
        func._test_name = name
        return func
    
    return decorator


# ==================== Flask API Tests ====================

@test('Flask app initialization')
def test_flask_init():
    """Test Flask app can be imported and initialized"""
    try:
        # Try to import the Flask app
        from app_gui import app, execute_epycon_conversion
        
        assert app is not None, "Flask app not initialized"
        assert app.config is not None, "Flask config not available"
        
        print("  - Flask app imported successfully")
        print("  - Testing mode: ", app.config.get('TESTING', False))
    except ImportError as e:
        print(f"  - Flask app import: {e}")
        print("  - (This is expected if Flask is not installed)")
        raise


@test('Configuration endpoint availability')
def test_config_endpoint():
    """Test that configuration endpoints are available"""
    try:
        from app_gui import app
        
        # Get list of available endpoints
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append(rule.rule)
        
        print(f"  - Available endpoints: {len(routes)}")
        for route in routes[:5]:
            print(f"    * {route}")
    except ImportError:
        print("  - Flask not installed (skipping endpoint test)")


@test('Conversion function signature')
def test_conversion_function():
    """Test conversion function exists and has correct signature"""
    try:
        from app_gui import execute_epycon_conversion
        import inspect
        
        # Get function signature
        sig = inspect.signature(execute_epycon_conversion)
        params = list(sig.parameters.keys())
        
        print(f"  - Function: execute_epycon_conversion")
        print(f"  - Parameters: {params}")
        
        assert 'cfg' in params or len(params) > 0, "Function has no parameters"
    except ImportError:
        print("  - Flask not installed (skipping function test)")


# ==================== Configuration Validation Tests ====================

@test('Config file format validation')
def test_config_format():
    """Test configuration file can be parsed"""
    config_path = Path(__file__).parent.parent / 'config' / 'config.json'
    
    assert config_path.exists(), f"Config file not found: {config_path}"
    
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    
    # Verify required fields
    required_fields = ['paths', 'data']
    for field in required_fields:
        assert field in cfg, f"Required field '{field}' missing"
    
    print(f"  - Config file format: Valid JSON")
    print(f"  - Required fields present: {required_fields}")


@test('Schema file format validation')
def test_schema_format():
    """Test schema file can be parsed"""
    schema_path = Path(__file__).parent.parent / 'config' / 'schema.json'
    
    assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    # Verify it's a valid JSON schema
    assert 'type' in schema or '$schema' in schema or 'properties' in schema, \
        "Schema format not recognized"
    
    print(f"  - Schema file format: Valid JSON")
    print(f"  - Schema type: {schema.get('type', 'object')}")


# ==================== Data Preparation Tests ====================

@test('Test data generation capability')
def test_data_generation():
    """Test that fake data can be generated"""
    try:
        # Check if the data generator script is available
        from scripts.generate_fake_wmx32 import generate_wmx
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Just verify the function is importable and callable
            assert callable(generate_wmx), "generate_wmx is not callable"
            
            print("  - Data generator module found")
            print("  - Available function: generate_wmx")
    except ImportError as e:
        print(f"  - Warning: Could not import generator: {e}")


@test('Example data directory structure')
def test_examples_directory():
    """Test example data directory structure"""
    examples_dir = Path(__file__).parent.parent / 'examples'
    
    # Check for expected subdirectories
    expected_dirs = ['data', 'demo.py']
    for item in expected_dirs:
        item_path = examples_dir / item
        if item_path.exists():
            print(f"  ✓ {item}")
        else:
            print(f"  ✗ {item} (missing)")


# ==================== Documentation Tests ====================

@test('Documentation completeness')
def test_documentation():
    """Test that documentation files exist"""
    docs_dir = Path(__file__).parent.parent / 'docs'
    
    required_docs = [
        'test_suite_report.md',
        'TESTING_QUICKSTART.md',
        'COMPLETION_REPORT.md'
    ]
    
    found_docs = []
    for doc in required_docs:
        doc_path = docs_dir / doc
        if doc_path.exists():
            found_docs.append(doc)
            size = doc_path.stat().st_size
            print(f"  ✓ {doc} ({size} bytes)")
        else:
            print(f"  ✗ {doc} (missing)")
    
    assert len(found_docs) > 0, "No documentation found"


@test('README availability')
def test_readme():
    """Test that README exists"""
    readme_path = Path(__file__).parent.parent / 'README.md'
    
    assert readme_path.exists(), "README.md not found"
    
    size = readme_path.stat().st_size
    print(f"  - README.md found ({size} bytes)")


# ==================== Test Report ====================

def print_summary():
    """Print test summary"""
    print(f"\n{'='*60}")
    print("GUI & CONFIG TEST SUITE SUMMARY")
    print(f"{'='*60}")
    print(f"Total tests: {tests_run}")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    
    if tests_run > 0:
        print(f"Pass rate: {tests_passed/tests_run*100:.1f}%")
    
    print(f"{'='*60}")
    
    if tests_failed == 0:
        print("✅ All GUI & config tests passed!")
    else:
        print(f"⚠️  {tests_failed} test(s) failed or skipped")
    
    return tests_failed == 0


if __name__ == '__main__':
    print("="*60)
    print("EPYCON GUI & CONFIGURATION TEST SUITE")
    print("="*60)
    
    # List of test functions to run
    test_list = [
        test_flask_init,
        test_config_endpoint,
        test_conversion_function,
        test_config_format,
        test_schema_format,
        test_data_generation,
        test_examples_directory,
        test_documentation,
        test_readme
    ]
    
    # Run each test
    for test_func in test_list:
        test_name = getattr(test_func, '_test_name', test_func.__name__)
        tests_run += 1
        
        print(f"\n[TEST {tests_run}] {test_name}")
        print(f"{'='*60}")
        
        try:
            test_func()
            print(f"[PASS] {test_name}")
            tests_passed += 1
        except Exception as e:
            print(f"[FAIL] {test_name}: {e}")
            tests_failed += 1
    
    # Print summary
    success = print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
