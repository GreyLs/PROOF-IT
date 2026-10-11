"""Offline protocol authoring/evaluation; outputs are machine-readable evidence.

Example: python -m scripts.prospective_validation protocol --input request.json --output protocol.json
Then: ... forms|macro --input {protocol,records}.json --output report.json
Independent source provenance and publication remain separate expert decisions.
"""
import argparse
import json
from pathlib import Path
from intelligence import prospective
from intelligence import experiments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('protocol', 'form-bundle', 'forms', 'macro', 'forecast'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error('Output must be a new file distinct from input')
    raw = args.input.read_bytes()
    if len(raw) > 8_000_000:
        parser.error('Input limit: 8 MB')
    payload = json.loads(raw)
    result = {'protocol': prospective.protocol, 'form-bundle': experiments.study_banks, 'forms': prospective.parallel_report,
              'macro': prospective.macro_ablation, 'forecast': prospective.forecast_report}[args.operation](payload)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')
    print(json.dumps({'operation': args.operation, 'output': str(args.output), 'production_activation_allowed': False}))


if __name__ == '__main__':
    main()
