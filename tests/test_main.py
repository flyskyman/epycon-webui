import sys
import json
from io import StringIO
from unittest.mock import patch, MagicMock
from epycon.cli.batch import parse_arguments


def test_parse_arguments_basic():
    """Test basic CLI argument parsing."""
    with patch('sys.argv', ['epycon', '-i', '/input', '-o', '/output', '-fmt', 'hdf']):
        args = parse_arguments()
        assert args.input_folder == '/input'
        assert args.output_folder == '/output'
        assert args.output_format == 'hdf'
        assert args.merge is False


def test_parse_arguments_merge():
    """Test merge flag parsing."""
    with patch('sys.argv', ['epycon', '--merge', '-i', '/input']):
        args = parse_arguments()
        assert args.merge is True


def test_parse_arguments_custom_config():
    """Test custom config path."""
    with patch('sys.argv', ['epycon', '--custom_config_path', '/config.json']):
        args = parse_arguments()
        assert args.custom_config_path == '/config.json'


from epycon.core.helpers import deep_override


import subprocess
import tempfile
import os


def test_cli_execution():
    """Test CLI execution with minimal config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, 'config.json')
        schema_path = os.path.join(tmpdir, 'schema.json')
        input_dir = os.path.join(tmpdir, 'input')
        output_dir = os.path.join(tmpdir, 'output')
        os.makedirs(input_dir)
        os.makedirs(output_dir)
        
        # Create minimal config
        config = {
            'paths': {
                'input_folder': input_dir,
                'output_folder': output_dir,
                'studies': []
            },
            'data': {
                'output_format': 'h5',
                'data_files': []
            },
            'global_settings': {'workmate_version': '4.3.2'}
        }
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Create minimal schema
        schema = {'type': 'object'}
        with open(schema_path, 'w') as f:
            json.dump(schema, f)
        
        # Run CLI with coverage
        project_root = os.path.dirname(os.path.dirname(__file__))
        result = subprocess.run([
            sys.executable, '-m', 'coverage', 'run', '--append', os.path.join(project_root, 'epycon', '__main__.py')
        ], env={
            **os.environ,
            'EPYCON_CONFIG': config_path,
            'EPYCON_JSONSCHEMA': schema_path,
            'PYTHONPATH': project_root
        }, capture_output=True, text=True, cwd=tmpdir)
        
        # Should exit with 0 and mention no log files
        assert result.returncode == 0
        assert '未找到 log 文件' in result.stdout or 'No valid datalog files' in result.stdout