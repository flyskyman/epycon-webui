import pytest
import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from epycon.__main__ import main as entry_point
import epycon.cli.run

class TestCLIIntegration:
    """Integration tests for the epycon CLI entry points."""

    @pytest.fixture
    def test_data(self):
        """Setup test data for CLI runs."""
        base_path = Path("examples/data/study01")
        if not base_path.exists():
            pytest.skip("Test data not found in examples/data/study01")
        return base_path

    def test_cli_help(self, capsys):
        """Test that --help argument works for main entry point."""
        with patch.object(sys, 'argv', ['epycon', '--help']):
            with pytest.raises(SystemExit) as excinfo:
                entry_point()
            assert excinfo.value.code == 0
        
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "usage:" in captured.err

    def test_cli_run_module_import(self):
        """Test that cli.run can be imported and main exists."""
        assert hasattr(epycon.cli.run, 'main')
        
    def test_cli_run_help(self, capsys):
        """Test that --help argument works for cli.run entry point."""
        # epycon.cli.run expects specific arguments or config, but --help should exit early
        with patch.object(sys, 'argv', ['run.py', '--help']):
            with pytest.raises(SystemExit) as excinfo:
                epycon.cli.run.main()
            assert excinfo.value.code == 0
            
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "usage:" in captured.err

    def test_cli_run_conversion(self, test_data, capsys):
        """Test a full conversion run via epycon.__main__.main CLI args."""
        with tempfile.TemporaryDirectory() as temp_out:
            # Setup environment to point to the correct config files
            env = os.environ.copy()
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            config_path = os.path.join(project_root, 'epycon', 'config', 'config.json')
            schema_path = os.path.join(project_root, 'epycon', 'config', 'schema.json')
            
            # Mock environment variables
            with patch.dict(os.environ, {
                'EPYCON_CONFIG': config_path,
                'EPYCON_JSONSCHEMA': schema_path
            }):
                # Construct CLI arguments
                # Simulate: epycon -i examples/data/study01 -o <temp_out> -fmt hdf -s study01
                # Note: input folder should be the PARENT of study01 for the logic to find study01 inside it?
                # Looking at __main__.py: iglob(os.path.join(input_folder, '**')) -> iterates subfolders.
                # So if input_folder is "examples/data", it finds "examples/data/study01".
                # Let's point input to examples/data
                
                input_dir = str(test_data.parent) # examples/data
                
                test_args = [
                    'epycon',
                    '-i', input_dir,
                    '-o', temp_out,
                    '-fmt', 'h5', 
                    '-e', 'True', # Convert entries
                    '-efmt', 'csv'
                ]

                
                # We need to ensure we use 'hdf' if that is the choice constraint, 
                # but internally it might map to 'h5'. 
                # Let's check batch.py if possible, or just try 'hdf'.
                
                with patch.object(sys, 'argv', test_args):
                    # We also need to mock or ensure batch.parse_arguments works.
                    # And ensure it doesn't default to something that breaks.
                    
                    try:
                        entry_point()
                    except SystemExit as e:
                        # It might exit 0 on success if sys.exit() is called, or just return.
                        # If it exits with non-zero, that's a failure.
                        assert e.code == 0
                    except Exception as e:
                        pytest.fail(f"CLI run failed with error: {e}")
                
                # Verify output was created
                # Expecting: temp_out/study01/00000000.h5
                study_out = Path(temp_out) / 'study01'
                assert study_out.exists(), "Output study directory not created"
                assert list(study_out.glob("*.h5")), "No HDF5 output files found"
                assert list(study_out.glob("*.csv")), "No Entry CSV output files found"

    def test_cli_run_merge_conversion(self, test_data, tmp_path):
        """Test merge mode: multiple logs combined into a single HDF5."""
        import json
        import h5py

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        base_config = os.path.join(project_root, 'epycon', 'config', 'config.json')
        schema_path = os.path.join(project_root, 'epycon', 'config', 'schema.json')

        with open(base_config) as f:
            cfg = json.load(f)
        cfg['paths']['input_folder'] = str(test_data.parent)
        cfg['paths']['output_folder'] = str(tmp_path)
        cfg['paths']['studies'] = ['study01']
        cfg['data']['merge_logs'] = True

        tmp_cfg = tmp_path / 'merge_config.json'
        tmp_cfg.write_text(json.dumps(cfg))

        with patch.dict(os.environ, {
            'EPYCON_CONFIG': str(tmp_cfg),
            'EPYCON_JSONSCHEMA': schema_path,
        }):
            with patch.object(sys, 'argv', ['epycon']):
                entry_point()

        merged = tmp_path / 'study01' / 'study01_merged.h5'
        assert merged.exists(), "Merged HDF5 not created"
        with h5py.File(merged, 'r') as f:
            assert 'Data' in f
            assert 'Info' in f
            # 两个示例日志各 1024 样本
            assert max(f['Data'].shape) == 2048
            # 回归断言：fixture 的两条 entries fid 都指向 00000001。
            # 第一条时间戳超出该文件时长，应被丢弃；第二条在文件起点后
            # 0.050s 处，应落在合并时间轴 1024(文件偏移) + 50(亚秒偏移) = 1074
            assert 'Marks' in f, "Entries were not injected into merged file"
            positions = [int(r['SampleLeft']) for r in f['Marks'][:]]
            assert positions == [1074], f"Expected mark at 1074, got {positions}"
