import sys
sys.dont_write_bytecode = True
import subprocess
import os
import tempfile
import shutil
import pathlib
import tarfile
import urllib.request
import urllib.parse
import urllib.error
import atexit
import socket
import time
from concurrent.futures import ThreadPoolExecutor

_PIP_DEPS = [
    'pyarrow',
    'numpy',
    'pandas',
    'questdb',
    'matplotlib',
    'jupyterlab',
    'requests']


_QUESTDB_VERSION = '6.7'
_QUESTDB_URL = (
    f'https://github.com/questdb/questdb/releases/download/{_QUESTDB_VERSION}' +
    f'/questdb-{_QUESTDB_VERSION}-no-jre-bin.tar.gz')


def find_java():
    search_path = None
    java_home = os.environ.get('JAVA_HOME')
    if java_home:
        search_path = pathlib.Path(java_home) / 'bin'
    return shutil.which('java', path=str(search_path))


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


class QuestDB:
    def __init__(self, tmpdir):
        self.java = find_java()
        self.tmpdir = tmpdir
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
        download_dir.mkdir()
        with urllib.request.urlopen(_QUESTDB_URL) as response, \
                open(archive_path, 'wb') as archive:
            shutil.copyfileobj(response, archive)
        print(f'Extracting QuestDB v.{_QUESTDB_VERSION} to {download_dir!r}.')
        with tarfile.open(archive_path) as tar:
            tar.extractall(self.questdb_path)
        questdb_bin_path = self.questdb_path / 'bin'
        # Rename "questdb-6.7-no-jre-bin" or similar to "bin"
        next(self.questdb_path.glob("**/questdb.jar")).parent.rename(questdb_bin_path)
        (self.questdb_path / 'data' / 'log').mkdir(parents=True)
        shutil.rmtree(download_dir, ignore_errors=True)

    def run_questdb(self):
        # TODO: This launch_args is Java11-specific. We should sniff the version and use the right args. 
        # We can probably use a simple "SniffVersion.class" to do this to export some metadata to json.
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
            f'http://localhost:9000/',  # TODO: Parameterize ports.
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
        self.proc.terminate()
        self.proc.wait()
        self.log_file.close()


def start_questdb(tmpdir):
    questdb = QuestDB(tmpdir)
    questdb.install()
    questdb.run()
    return questdb


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
    subprocess.run(
        [str(tmpdir / 'venv' / 'Scripts' / 'pip'), 'install'] + _PIP_DEPS,
        cwd=str(venv_dir),
        check=True)


def check_python_version():
    if sys.version_info < (3, 8):
        print('Python 3.8 or later is required')
        sys.exit(1)


def check_java_version():
    java = find_java()
    java_version = subprocess.run(
        [str(java), '-version'],
        stderr=subprocess.PIPE,
        check=True,
        encoding='utf-8')
    if '11.' not in java_version.stderr:
        print('Java 11 is required')
        sys.exit(1)


@with_tmpdir
def main(tmpdir):
    write_readme(tmpdir)
    tpe = ThreadPoolExecutor()

    start_fut = tpe.submit(start_questdb, tmpdir)
    setup_venv(tmpdir)
    questdb = start_fut.result()
    import code
    code.interact(local=locals(), banner='QuestDB is running. Press Ctrl-D to exit.')


if __name__ == '__main__':
    check_python_version()
    check_java_version()
    main()
