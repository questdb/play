#!/usr/bin/env python3
import run
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor


def main():
    tpe = ThreadPoolExecutor()
    questdb = run.QuestDB(
        java_path=Path('/usr/lib/jvm/java-17-amazon-corretto/bin/java'),
        questdb_path=Path('/opt/questdb'))
    questdb.configure()
    lab = run.JupyterLab(
        script_path=Path('/usr/local/bin/jupyter-lab'),
        notebook_dir=Path('/opt/notebooks'),
        log_path=Path('/opt/jupyterlab.log'))
    lab.configure(questdb)
    questdb_run_fut = tpe.submit(questdb.run)
    lab_run_fut = tpe.submit(lab.run)
    questdb_run_fut.result()
    lab_run_fut.result()
    hostname = lab.hostname

    print('\n\nQuestDB and JupyterLab are now running...')
    print(f' * JupyterLab: {lab.url}')
    print(' * QuestDB:')
    print(
        f'    * Web Console / REST API: http://{hostname}:' +
        f'{questdb.http_port}/')
    print(
        f'    * PSQL: psql -h {hostname} -p {questdb.pg_port} ' +
        '-U admin -d qdb  # password: quest')
    print(f'    * ILP Protocol, port: {questdb.ilp_port}')
    print()
    print('>>>>> CLICK THE FIRST LINK ABOVE TO OPEN JUPYTERLAB <<<<<')
    print()

    run.wait_prompt()
    run.print_exit_message()


if __name__ == '__main__':
    main()
