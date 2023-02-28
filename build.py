#!/usr/bin/env python3

import subprocess
import shutil
import pathlib


def main():
    shutil.rmtree('output', ignore_errors=True)
    pathlib.Path('output').mkdir(parents=True)

    args = ['jupyter', 'nbconvert',
            '--to', 'html',
            '--template', 'lab',
            '--output-dir', '../output',
            '--output', 'index',
            'play.ipynb']
    subprocess.run(args, check=True, cwd='notebooks')


if __name__ == "__main__":
    main()
