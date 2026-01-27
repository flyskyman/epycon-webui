import argparse

parser = argparse.ArgumentParser()

def parse_arguments():
    """ Custom CLI definition

    Returns:
        parser: CLI arguments
    """
    # Input and output folder paths    
    parser.add_argument("-i", "--input_folder", type=str,)
    parser.add_argument("-o", "--output_folder", type=str,)
    
    # List of studies that will be exported. All if not provided.
    parser.add_argument("-s", "--studies", type=list,)

    # Output format of the waveforms
    parser.add_argument("-fmt", "--output_format", type=str, choices=['csv', 'hdf'])

    # Output format of the entries/annotations
    parser.add_argument("-e", "--entries", type=bool,)
    parser.add_argument("-efmt", "--entries_format", type=str, choices=['csv', 'sel'])

    # Overwrite settings with custom config file
    parser.add_argument("--custom_config_path", type=str, help="Path to configuration file")

    # Merge multiple log files into a single HDF5 output (V68.4 Feature)
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge all log files in each study into a single HDF5 file. "
             "Files are concatenated by timestamp order."
    )

    return parser.parse_args()
