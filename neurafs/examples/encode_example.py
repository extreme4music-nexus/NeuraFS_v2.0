"""NeuraFS Simple Encoding Example."""

from neurafs.sdk import NeuraFSSDK

# Programmatic encoding example
input_file = "sample.wav"
output_container = "sample.hcs"

# To run this example, ensure sample.wav exists locally
# result = NeuraFSSDK.encode_file(input_file, output_container, precision="fp16")
# print(f"Encoded HCS container created: {result['output_path']}")