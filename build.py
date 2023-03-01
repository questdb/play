#!/usr/bin/env python3

import subprocess


def main():
    args = ['jupyter', 'nbconvert',
            '--to', 'html',
            '--template', 'lab',
            '--output-dir', '../',
            '--output', 'index',
            'play.ipynb']
    subprocess.run(args, check=True, cwd='notebooks')


if __name__ == "__main__":
    main()
