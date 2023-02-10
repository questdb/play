## Script

**run.py** sets up the environment required to run [QuestDB 6.7](https://github.com/questdb/questdb/releases/tag/6.7/)
alongside a [Jupyter-lab](https://jupyter.org/try-jupyter/lab/) environment, for the purpose of showcasing QuestDB's
superior data analytics capabilities, when compared to a Pandas DataFrame.

A local ephemeral directory is created to host a Python 3.10 virtual environment, plus Java 11 JRE.

## Docker

### Build image

```shell
docker build -t io.questdb.play:1.0-SNAPSHOT .
```

### Run container

```shell
  docker run --rm \
    -p 8888:8888 \
    -p 8812:8812 \
    -p 9009:9009 \
    -p 9000:9000 \
    --name questdb-play \
    -it io.questdb.play:1.0-SNAPSHOT [bash]
```

Mount points:

- **/opt/questdb/**:  QuestDB's root directory.
- **/opt/questdb/db/**:  QuestDB's data root directory.
- **/opt/backups/**: Directory for backups.
- **/opt/csv/**: Directory for backups.
- **/opt/volume0/**: Additional volume for create table, alias volume0.
- **/opt/volume1/**: Additional volume for create table, alias volume1.
- **/opt/notebooks/**: Jupyter notebooks.

```shell
  docker run --rm \
    -p 8888:8888 \
    -p 8812:8812 \
    -p 9009:9009 \
    -p 9000:9000 \
    --name questdb-play \
    -v /Users/marregui/QUEST/db:/opt/questdb/db \
    -v /Users/marregui/QUEST/notebooks:/opt/notebooks \
    -v /Users/marregui/QUEST/backups:/opt/backups \
    -v /Users/marregui/QUEST/csv:/opt/csv \
    -v /Users/marregui/OTHER/volume0:/opt/volume0 \
    -v /Users/marregui/OTHER/volume1:/opt/volume1 \
    -it io.questdb.play:1.0-SNAPSHOT
```

### Delete image

```shell
docker rmi -f io.questdb.play:1.0-SNAPSHOT
docker rmi -f $(docker images -a | grep none | sed 's/  */|/g' | cut -f 3 -d'|')
```

## Notes

To test the _index.html_ command locally:

```shell
python3 -c "exec(open('run.py', 'r').read())"
```

should be equivalent to:

```shell
python3 -c "import urllib.request as w;s=w.urlopen('https://dl.questdb.io/play/run.py').read().decode();exec(s)
```
