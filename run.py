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
import webbrowser
import textwrap
from concurrent.futures import ThreadPoolExecutor

_IN_DOCKER = False
_PIP_DEPS = [
    'certifi',
    'pillow',
    'pyarrow',
    'numpy',
    'pandas',
    'questdb',
    'matplotlib',
    'jupyterlab',
    'requests',
    'psycopg[binary]'
]
_QUESTDB_VERSION = '6.7'
_QUESTDB_URL = (
        f'https://github.com/questdb/questdb/releases/download/{_QUESTDB_VERSION}' +
        f'/questdb-{_QUESTDB_VERSION}-no-jre-bin.tar.gz')
_URL_HTTPS_CONTEXT = None


def wait_prompt():
    print('Press Ctrl+C to exit.')
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    print('\nStopping services, deleting temporary files and exiting.')


def avail_port():
    s = socket.socket()
    try:
        s.bind(('', 0))
        return s.getsockname()[1]
    finally:
        s.close()


def ping_retry(
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
    with urllib.request.urlopen(url, context=_URL_HTTPS_CONTEXT) as resp, open(dest_path, 'wb') as dest:
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


def tail_log(path, lines=30):
    log = 'No log available.'
    try:
        with open(path, 'r', encoding='utf-8') as log_file:
            log = log_file.readlines()[-lines:]
        log = ''.join(log)
        log = textwrap.indent(log, '    ')
        log = f'Tail of log:\n{log}'
    except:
        pass
    return log


class QuestDB:
    def __init__(self, tmpdir, java_path=None, jar_path=None):
        self.tmpdir = tmpdir
        if sys.platform == 'win32':
            self.java = tmpdir / 'jre' / 'bin' / 'java.exe'
        else:
            if java_path is None:
                self.java = tmpdir / 'jre' / 'bin' / 'java'
            else:
                self.java = java_path
        self.questdb_path = tmpdir / 'questdb'
        self.jar_path = self.questdb_path / 'bin' / 'questdb.jar' if jar_path is None else jar_path
        self.data_path = self.questdb_path / 'data'
        self.log_path = self.data_path / 'log' / 'questdb.log'
        self.proc = None
        self.log_file = None

    def install(self):
        print(f'Downloading QuestDB v.{_QUESTDB_VERSION} from {_QUESTDB_URL!r}.')
        download_dir = self.tmpdir / 'download'
        if not download_dir.is_dir():
            download_dir.mkdir()
        archive_path = download_dir / 'questdb.tar.gz'
        download(_QUESTDB_URL, archive_path)
        print(f'Extracting QuestDB v.{_QUESTDB_VERSION} to {download_dir!r}.')
        with tarfile.open(archive_path) as tar:
            tar.extractall(self.questdb_path)
        questdb_bin_path = self.questdb_path / 'bin'
        # Rename "questdb-6.7-no-jre-bin" or similar to "bin"
        next(self.questdb_path.glob("**/questdb.jar")).parent.rename(questdb_bin_path)
        self.configure()

    def configure(self):
        (self.questdb_path / 'data' / 'log').mkdir(parents=True)
        if _IN_DOCKER:
            self.ilp_port = 9009
            self.pg_port = 8812
            self.http_port = 9000
            self.http_min_port = 9003
        else:
            self.ilp_port = avail_port()
            self.pg_port = avail_port()
            self.http_port = avail_port()
            self.http_min_port = avail_port()
            overrides = {
                'http.bind.to': f'127.0.0.1:{self.http_port}',
                'pg.net.bind.to': f'127.0.0.1:{self.pg_port}',
                'line.tcp.net.bind.to': f'127.0.0.1:{self.ilp_port}',
                'line.udp.bind.to': f'127.0.0.1:{self.ilp_port}',
                'http.min.net.bind.to': f'127.0.0.1:{self.http_min_port}',
            }
            self.override_conf(overrides)

    def override_conf(self, overrides):
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
            '-Xms3g',
            '-Xmx3g',
            '-Dfile.encoding=UTF-8',
            '--add-reads',
            'io.questdb=ALL-UNNAMED',
            '-ea',
            '-Debug',
            '-XX:+UnlockExperimentalVMOptions',
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
        ping_retry(
            self.check_http_up,
            timeout_sec=60,
            msg='Timed out waiting for HTTP service to come up.')
        print('QuestDB is up.')

    def check_http_up(self):
        if self.proc.poll() is not None:
            log = tail_log(self.log_path)
            raise RuntimeError(f'QuestDB died during startup. {log}')
        req = urllib.request.Request(
            f'http://localhost:{self.http_port}/',
            method='HEAD')
        try:
            resp = urllib.request.urlopen(req, context=_URL_HTTPS_CONTEXT, timeout=1)
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
    def __init__(self, tmpdir, script_dir=None):
        self.tmpdir = tmpdir
        if script_dir is None:
            self.script = self.tmpdir / 'venv' / 'Scripts' / 'jupyter-lab' \
                if sys.platform == 'win32' else self.tmpdir / 'venv' / 'bin' / 'jupyter-lab'
        else:
            self.script = script_dir
        self.log_path = self.tmpdir / 'jupyterlab.log'
        self.notebook_dir = self.tmpdir / 'notebooks'
        self.play_notebook_path = self.notebook_dir / 'play.ipynb'
        self.log_file = None
        self.proc = None
        self.host_log_search = 'localhost'
        self.port = None
        self.url = None

    def install(self):
        # TODO: Wire-up dynamic ports from QuestDB into `play.ipynb`.
        if os.environ.get('LOCAL_RUN') == '1':
            self.notebook_dir = pathlib.Path(__file__).parent / 'notebooks'
        else:
            if not self.notebook_dir.is_dir():
                self.notebook_dir.mkdir()
            download('https://dl.questdb.io/play/notebooks/play.ipynb', self.play_notebook_path)

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
        if _IN_DOCKER:
            self.port = 8888
        else:
            self.port = avail_port()
        self.log_file = open(self.log_path, 'ab')
        command = [str(self.script)]
        if _IN_DOCKER:
            command.append('--allow-root')
            command.append('--ip')
            command.append('0.0.0.0')
            self.host_log_search = '127.0.0.1'
        command.append('--port')
        command.append(str(self.port))
        command.append('--no-browser')
        command.append('--notebook-dir')
        command.append(str(self.notebook_dir))
        command.append(str(self.play_notebook_path))
        print(f'jupyter-lab command: {" ".join(command)}')
        self.proc = subprocess.Popen(
            command,
            close_fds=True,
            cwd=self.notebook_dir,
            stdout=self.log_file,
            stderr=subprocess.STDOUT)
        atexit.register(self.stop)
        self.discover_url()

    def scan_log_for_url(self):
        if self.proc.poll() is not None:
            log = tail_log(self.log_path)
            raise RuntimeError(f'JupyterLab died during startup. {log}')
        target_log = f'http://{self.host_log_search}:{self.port}/lab?token='
        with open(self.log_path, 'r') as log_file:
            for line in log_file:
                if target_log in line:
                    self.url = line.strip().replace(self.host_log_search, 'localhost')
                    print(f'JupyterLab URL: {self.url}')
                    return True
        return False

    def discover_url(self):
        print('Waiting until JupyterLab URL is available.')
        ping_retry(
            self.scan_log_for_url,
            timeout_sec=30,
            msg='Timed out waiting for JupyterLab URL to become available.')
        print('JupyterLab URL is available.')

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


def write_readme():
    with open('PLAY_QUESTDB_README.txt', 'w') as readme:
        readme.write(
            '''Directory and contents created by https://play.questdb.io/
            If you don't recognize this directory, you can safely delete it.''')


def setup_venv(tmpdir):
    venv_dir = tmpdir / 'venv'
    subprocess.run([sys.executable, '-m', 'venv', str(venv_dir)], check=True)
    python3_path = str(next(venv_dir.glob("**/python3")))
    subprocess.run([python3_path, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
    subprocess.run(
        [
            str(next(venv_dir.glob("**/pip3"))),
            'install',
            '--no-warn-script-location',
            '--no-input',
            '--no-compile',
            '--only-binary',
            ':all:'
        ] + _PIP_DEPS,
        cwd=str(venv_dir),
        check=True)


def check_python_version():
    if sys.version_info < (3, 8):
        print('Python 3.8 or later is required.')
        sys.exit(1)


_ASK_PROMPT = f'''
In a temporary directory, this script will:
    * Download and run QuestDB {_QUESTDB_VERSION}.
    * Create a Python virtual environment in the same directory.
        * `pip install`: {_PIP_DEPS}.
    * Launch a Jupyter notebook in a new browser window.

The directory will be automatically deleted when you exit this script.

Continue? [Y/n] '''


def try_open_browser(url):
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        pass


@with_tmpdir
def main(tmpdir):
    write_readme()
    download_dir = tmpdir / 'download'
    download_dir.mkdir()
    tpe = ThreadPoolExecutor()
    questdb = QuestDB(tmpdir)
    install_java_fut = tpe.submit(install_java, tmpdir)
    install_questdb_fut = tpe.submit(questdb.install)
    setup_venv(tmpdir)
    install_java_fut.result()
    install_questdb_fut.result()
    lab = JupyterLab(tmpdir)
    lab.install()
    lab.configure(questdb)
    lab.run()
    questdb.run()
    print('\n\nQuestDB and JupyterLab are now running...')
    print(f' * Temporary directory: {tmpdir}')
    print(f' * JupyterLab: {lab.url}')
    print(f' * QuestDB:')
    print(f'    * Web Console / REST API: http://localhost:{questdb.http_port}/')
    print(f'    * PSQL: psql -h localhost -p {questdb.pg_port} -U admin -d qdb')
    print(f'    * ILP Protocol, port: {questdb.ilp_port}')
    print('\n')
    try_open_browser(lab.url)
    wait_prompt()
    lab.stop()
    questdb.stop()


def main_in_docker():
    opt_dir = pathlib.Path('/opt')
    jupyter_lab_dir = opt_dir / 'venv' / 'bin' / 'jupyter-lab'
    download_dir = pathlib.Path('download')
    download_dir.mkdir(parents=True)
    with ThreadPoolExecutor() as tpe:
        questdb = QuestDB(
            opt_dir,
            java_path=pathlib.Path('/usr/lib/jvm/java-17-amazon-corretto/bin/java'),
            jar_path=pathlib.Path('/opt/questdb/questdb.jar'))
        questdb.configure()
        lab = JupyterLab(opt_dir, jupyter_lab_dir)
        lab.install()
        lab.configure(questdb)
        lab.run()
    print('\n\nQuestDB and JupyterLab are now running...')
    print(f' * JupyterLab: {lab.url}')
    print(f' * QuestDB:')
    print(f'    * Web Console / REST API: http://localhost:{questdb.http_port}/')
    print(f'    * PSQL: psql -h localhost -p {questdb.pg_port} -U admin -d qdb')
    print(f'    * ILP Protocol, port: {questdb.ilp_port}')
    print('\n')
    wait_prompt()
    try:
        lab.stop()
        questdb.stop()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    _IN_DOCKER = 'IN_DOCKER' in sys.argv
    if not _IN_DOCKER:
        # if input(_ASK_PROMPT).lower().strip() not in ('y', ''):
        #     print('Aborted')
        #     sys.exit(1)

        import certifi
        import ssl

        _URL_HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        check_python_version()
        main()
    else:
        main_in_docker()
    print('\nThanks for trying QuestDB!\n')
    print('Learn more:')
    print(' * https://questdb.io/docs/')
    print(' * https://questdb.io/cloud/')
    print(' * https://slack.questdb.io/')
    print('')
