#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys

sys.dont_write_bytecode = True


AWS_PROFILE = 'sso-main'


PATHS = [
    'jre/linux-x86_64.tar.gz',
    'jre/win32-AMD64.zip',
    'jre/linux-aarch64.tar.gz',
    'jre/README.md',
    'jre/darwin-arm64.tar.gz',
    'jre/darwin-x86_64.tar.gz',
    'run.py',
    'notebooks/play.ipynb',
    'notebooks/energy.parquet.gzip',]


def upload(paths):
    for path in paths:
        if path not in PATHS:
            raise ValueError(f'Path {path} is not in PATHS')
    for path in paths:
        print(f'Copying {path} to S3...')
        ran = subprocess.run([
            'aws', 's3',
            'cp', path, f's3://questdb/play/{path}',
            '--profile', AWS_PROFILE])
        if ran.returncode != 0:
            print('')
            print(f'Failed to upload {path}')
            print('If this was due to an expired token, run:')
            print(f'    aws sso login --profile {AWS_PROFILE}')
            sys.exit(1)
        print('')


def invalidate_cloudfront(paths):
    print('Invalidating CloudFront cache...')
    subprocess.run([
        'aws', 'cloudfront',
        'create-invalidation',
        '--distribution-id', os.environ['CLOUDFRONT_DISTRIBUTION_ID'],
        '--paths'] + [f'/play/{path}' for path in paths] + [
        '--profile', AWS_PROFILE], check=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--files', nargs='+', default=PATHS,
        help=f'Files to upload to S3, any of: {PATHS!r}')
    return parser.parse_args()


def main():
    args = parse_args()
    if 'CLOUDFRONT_DISTRIBUTION_ID' not in os.environ:
        print('CLOUDFRONT_DISTRIBUTION_ID is not set')
        sys.exit(1)
    upload(args.files)
    invalidate_cloudfront(args.files)


if __name__ == '__main__':
    main()
