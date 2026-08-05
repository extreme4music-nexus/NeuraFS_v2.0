"""NeuraFS Command Line Utility Interface."""

import argparse
import json
import sys

from neurafs.sdk.python.sdk import NeuraFSSDK


def main():
    parser = argparse.ArgumentParser(description="NeuraFS Neural Media Storage CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Encode media file to .hcs container")
    encode_parser.add_argument("input", help="Path to input audio file")
    encode_parser.add_argument("output", help="Path to output .hcs container")
    encode_parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode .hcs container to .wav")
    decode_parser.add_argument("input", help="Path to input .hcs container")
    decode_parser.add_argument("output", help="Path to output .wav file")

    # Inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect .hcs container metadata")
    inspect_parser.add_argument("input", help="Path to .hcs container")

    args = parser.parse_args()

    if args.command == "encode":
        res = NeuraFSSDK.encode_file(args.input, args.output, precision=args.precision)
        print(f"[Success] Encoded container saved to: {res['output_path']}")
    elif args.command == "decode":
        res = NeuraFSSDK.decode_to_wav(args.input, args.output)
        print(f"[Success] Reconstructed WAV saved to: {res['output_path']}")
    elif args.command == "inspect":
        manifest = NeuraFSSDK.inspect(args.input)
        print(json.dumps(manifest, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()