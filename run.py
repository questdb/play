#!/usr/bin/env python3

import sys
import subprocess
import os
import tempfile
import shutil
import pathlib
import tarfile
import zipfile
import urllib.request
import urllib.parse
import urllib.error
import atexit
import socket
import time
import json
import platform
from concurrent.futures import ThreadPoolExecutor


_PIP_DEPS = [
    'pyarrow',
    'numpy',
    'pandas',
    'questdb',
    'matplotlib',
    'jupyterlab',
    'requests',
    'psycopg[binary]']


_QUESTDB_VERSION = '6.7'
_QUESTDB_URL = (
    f'https://github.com/questdb/questdb/releases/download/{_QUESTDB_VERSION}' +
    f'/questdb-{_QUESTDB_VERSION}-no-jre-bin.tar.gz')


def wait_prompt():
    print('Press Ctrl+C to exit.')
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    print('Stopping services, deleting temporary files and exiting.')


def avail_port():
    s = socket.socket()
    try:
        s.bind(('', 0))
        return s.getsockname()[1]
    finally:
        s.close()


def retry(
    predicate_task,
    timeout_sec=30,
    every=0.05,
    msg='Timed out retrying',
    backoff_till=5.0,
    lead_sleep=0.1):
    """
    Repeat task every `interval` until it returns a truthy value or times out.
    """
    begin = time.monotonic()
    threshold = begin + timeout_sec
    if lead_sleep:
        time.sleep(lead_sleep)
    while True:
        res = predicate_task()
        if res:
            return res
        elif time.monotonic() < threshold:
            time.sleep(every)
            if backoff_till:
                every = min(backoff_till, every * 1.25)
        else:
            raise TimeoutError(msg)


def download(url, dest_path):
    with urllib.request.urlopen(url) as resp, open(dest_path, 'wb') as dest:
        shutil.copyfileobj(resp, dest)


def first_dir(path):
    return next(path.iterdir())


def install_java(tmpdir):
    print('Downloading and installing Java 11.')
    platform_id = f'{sys.platform}-{platform.machine()}'
    is_windows = sys.platform == 'win32'
    fname = f'{platform_id}.zip' if is_windows else f'{platform_id}.tar.gz'
    url = f'https://dl.questdb.io/play/jre/{fname}'
    download_dir = tmpdir / 'download'
    extraction_dir = tmpdir / 'download' / 'jre'
    extraction_dir.mkdir()
    archive_path = download_dir / fname
    download(url, archive_path)
    if is_windows:
        with zipfile.ZipFile(archive_path) as zip:
            zip.extractall(extraction_dir)
    else:
        with tarfile.open(archive_path) as tar:
            tar.extractall(extraction_dir)
    unpacked_jre_dir = first_dir(extraction_dir)
    if sys.platform == 'darwin':
        unpacked_jre_dir = unpacked_jre_dir / 'Contents' / 'Home'
    shutil.move(unpacked_jre_dir, tmpdir / 'jre')


class QuestDB:
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
        if sys.platform == 'win32':
            self.java = tmpdir / 'jre' / 'bin' / 'java.exe'
        else:
            self.java = tmpdir / 'jre' / 'bin' / 'java'
        self.questdb_path = tmpdir / 'questdb'
        self.jar_path = self.questdb_path / 'bin' / 'questdb.jar'
        self.data_path = self.questdb_path / 'data'
        self.log_path = self.data_path / 'log' / 'questdb.log'
        self.proc = None
        self.log_file = None

    def install(self):
        print(f'Downloading QuestDB v.{_QUESTDB_VERSION} from {_QUESTDB_URL!r}.')
        download_dir = self.tmpdir / 'download'
        archive_path = download_dir / 'questdb.tar.gz'
        download(_QUESTDB_URL, archive_path)
        print(f'Extracting QuestDB v.{_QUESTDB_VERSION} to {download_dir!r}.')
        with tarfile.open(archive_path) as tar:
            tar.extractall(self.questdb_path)
        questdb_bin_path = self.questdb_path / 'bin'
        # Rename "questdb-6.7-no-jre-bin" or similar to "bin"
        next(self.questdb_path.glob("**/questdb.jar")).parent.rename(questdb_bin_path)
        (self.questdb_path / 'data' / 'log').mkdir(parents=True)
        self.configure()

    def configure(self):
        self.ilp_port = avail_port()
        self.pg_port = avail_port()
        self.http_port = avail_port()
        self.http_min_port = avail_port()
        overrides = {
            'http.bind.to': f'0.0.0.0:{self.http_port}',
            'pg.net.bind.to': f'0.0.0.0:{self.pg_port}',
            'line.tcp.net.bind.to': f'0.0.0.0:{self.ilp_port}',
            'line.udp.bind.to': f'0.0.0.0:{self.ilp_port}',
            'http.min.bind.to': f'0.0.0.0:{self.http_min_port}',
        }
        # No conf file extracted from the tarball, so we'll create one.
        # We pluck it out of the .jar and the patch it.
        with zipfile.ZipFile(self.jar_path) as zip:
            conf_lines = zip.read('io/questdb/site/conf/server.conf')
            conf_lines = conf_lines.decode('utf-8').splitlines()
        conf_path = self.questdb_path / 'data' / 'conf' / 'server.conf'
        conf_path.parent.mkdir(parents=True)
        with conf_path.open('w', encoding='utf-8') as conf:
            for line in conf_lines:
                if ('=' in line) and (line.split('=')[0] in overrides):
                    # Comment out lines we'll override.
                    conf.write(f'#{line}')
                conf.write(line)
            conf.write('\n# Dynamic ports configuration\n')
            for key, value in overrides.items():
                conf.write(f'{key}={value}\n')

    def run(self):
        launch_args = [
            self.java,
            '-DQuestDB-Runtime-0',
            '-ea',
            #'-Dnoebug',
            '-Debug',
            '-XX:+UnlockExperimentalVMOptions',
            '-XX:+AlwaysPreTouch',
            '-XX:+UseParallelOldGC',
            '-p', str(self.jar_path),
            '-m', 'io.questdb/io.questdb.ServerMain',
            '-d', str(self.data_path)]
        sys.stderr.write(
            f'Starting QuestDB: {launch_args!r}\n')
        self.log_file = open(self.log_path, 'ab')
        self.proc = subprocess.Popen(
            launch_args,
            close_fds=True,
            cwd=self.data_path,
            # env=launch_env,
            stdout=self.log_file,
            stderr=subprocess.STDOUT)

        atexit.register(self.stop)

        print('Waiting until QuestDB HTTP service is up.')
        retry(
            self.check_http_up,
            timeout_sec=60,
            msg='Timed out waiting for HTTP service to come up.')
        print('QuestDB is up.')

    def check_http_up(self):
        if self.proc.poll() is not None:
            raise RuntimeError('QuestDB died during startup.')
        req = urllib.request.Request(
            f'http://localhost:{self.http_port}/',
            method='HEAD')
        try:
            resp = urllib.request.urlopen(req, timeout=1)
            if resp.status == 200:
                return True
        except socket.timeout:
            pass
        except urllib.error.URLError:
            pass
        return False

    def stop(self):
        # Idempotent.
        if self.proc is None:
            return
        self.proc.terminate()
        self.proc.wait()
        self.log_file.close()
        self.proc = None
        self.log_file = None


class JupyterLab:
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
        self.notebook_dir = None
        self.script = None
        self.log_path = self.tmpdir / 'jupyterlab.log'
        self.log_file = None
        self.proc = None
        self.play_notebook_path = None
        self.port = None

    def install(self):
        # TODO: Wire-up dynamic ports from QuestDB into `play.ipynb`.
        self.script = self.tmpdir / 'venv' / 'Scripts' / 'jupyter-lab' \
            if sys.platform == 'win32' else self.tmpdir / 'venv' / 'bin' / 'jupyter-lab'
        if os.environ.get('LOCAL_RUN') == '1':
            self.notebook_dir = pathlib.Path(__file__).parent / 'notebooks'
            self.play_notebook_path = self.notebook_dir / 'play.ipynb'
        else:
            self.notebook_dir = self.tmpdir / 'notebooks'
            self.notebook_dir.mkdir()
            self.play_notebook_path = self.notebook_dir / 'play.ipynb'
            download(
                'https://dl.questdb.io/play/notebooks/play.ipynb',
                self.play_notebook_path)

    def configure(self, questdb):
        with self.play_notebook_path.open('r') as play_file:
            play = json.load(play_file)

            # Patch up the contents of the second cell.
            play['cells'][2]['source'] = [
                '# This demo relies on dynamic network ports for the core endpoints.\n',
                f'http_port = {questdb.http_port}  # Web Console and REST API\n',
                f'ilp_port = {questdb.ilp_port}  # Fast data ingestion port \n',
                f'pg_port = {questdb.pg_port}  # PostgreSQL-compatible endpoint']
        with self.play_notebook_path.open('w') as play_file:
            json.dump(play, play_file, indent=1, sort_keys=True)

    def run(self):
        self.port = avail_port()
        self.log_file = open(self.log_path, 'ab')
        self.proc = subprocess.Popen(
            [str(self.script), '--port', str(self.port)],
            close_fds=True,
            cwd=self.notebook_dir,
            stdout=self.log_file,
            stderr=subprocess.STDOUT)

        atexit.register(self.stop)

    def stop(self):
        # Idempotent.
        if self.proc is None:
            return
        self.proc.terminate()
        self.proc.wait()
        self.log_file.close()
        self.proc = None
        self.log_file = None


def with_tmpdir(fn):
    def wrapper(*args, **kwargs):
        tmpdir = tempfile.mkdtemp(prefix='questdb_play_')
        tmpdir = pathlib.Path(tmpdir)
        print(f'Created temporary directory: {tmpdir}')
        try:
            return fn(tmpdir, *args, **kwargs)
        finally:
            shutil.rmtree(str(tmpdir))
            print(f'Deleted temporary directory: {tmpdir}')
    return wrapper


def write_readme(tmpdir):
    with open('README.txt', 'w') as readme:
        readme.write(
            '''Directory and contents created by https://play.questdb.io/
            If you don't recognize this directory, you can safely delete it.''')


def setup_venv(tmpdir):
    venv_dir = tmpdir / 'venv'
    subprocess.run(
        [sys.executable, '-m', 'venv', str(venv_dir)],
        check=True)
    pip_path = venv_dir / 'Scripts' / 'pip' \
        if sys.platform == 'win32' else venv_dir / 'bin' / 'pip'
    subprocess.run(
        [str(pip_path), 'install', '--only-binary', ':all:'] + _PIP_DEPS,
        cwd=str(venv_dir),
        check=True)


def check_python_version():
    if sys.version_info < (3, 8):
        print('Python 3.8 or later is required')
        sys.exit(1)


_ASK_PROMPT = f'''
In a temporary directory, this script will:
    * Download and run QuestDB {_QUESTDB_VERSION}.
    * Create a Python virtual environment in the same directory.
        * `pip install`: {_PIP_DEPS}.
    * Launch a Jupyter notebook in a new browser window.

The directory will be automatically deleted when you exit this script.

Continue? [Y/n] '''


def start_jupyter_lab(tmpdir, questdb):
    lab = JupyterLab(tmpdir)
    lab.install()
    lab.configure(questdb)
    lab.run()
    return lab


@with_tmpdir
def main(tmpdir):
    write_readme(tmpdir)
    download_dir = tmpdir / 'download'
    download_dir.mkdir()
    tpe = ThreadPoolExecutor()
    questdb = QuestDB(tmpdir)
    install_java_fut = tpe.submit(install_java, tmpdir)
    install_questdb_fut = tpe.submit(questdb.install)
    setup_venv(tmpdir)
    install_java_fut.result()
    install_questdb_fut.result()
    lab = start_jupyter_lab(tmpdir, questdb)
    questdb.run()
    time.sleep(3)  # A few seconds for the Web browser to start up.
    print('\n\nQuestDB and JupyterLab are now running...')
    wait_prompt()
    lab.stop()
    questdb.stop()


if __name__ == '__main__':
    if input(_ASK_PROMPT).lower().strip() not in ('y', ''):
        print('Aborted')
        sys.exit(1)
    check_python_version()
    main()
    print('\nThanks for trying QuestDB!\n')
    print('Learn more:')
    print(' * https://questdb.io/docs/')
    print(' * https://questdb.io/cloud/')
    print(' * https://slack.questdb.io/')
    print('')
