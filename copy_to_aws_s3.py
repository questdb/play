#!/usr/bin/env python3

import subprocess
AWS_PROFILE='sso-main'

paths = [
    'jre/linux-x86_64.tar.gz',
    'jre/win32-AMD64.zip',
    'jre/linux-aarch64.tar.gz',
    'jre/README.md',
    'jre/darwin-arm64.tar.gz',
    'jre/darwin-x86_64.tar.gz',
    'run.py',
    'notebooks/play.ipynb']

for path in paths:
    print(f'Copying {path} to S3...')
    subprocess.run([
        'aws', 's3',
        'cp', path, f's3://questdb/play/{path}',
        '--profile', AWS_PROFILE])
    print('')
