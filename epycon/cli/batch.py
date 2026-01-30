import argparse

def parse_arguments():
    """ Custom CLI definition

    Returns:
        parser: CLI arguments
    """
    # Create a new parser instance each time to avoid conflicts
    parser = argparse.ArgumentParser()
    
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
    
    # Merge mode - combine multiple log files into one output
    parser.add_argument("--merge", action="store_true", help="Merge multiple log files into a single output file")

    # Overwrite settings with custom config file
    parser.add_argument("--custom_config_path", type=str, help="Path to configuration file")

    return parser.parse_args()
