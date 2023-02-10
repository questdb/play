## Script

**run.py** sets up the environment required to run [QuestDB 6.7](https://github.com/questdb/questdb/releases/tag/6.7/)
alongside a [Jupyter-lab](https://jupyter.org/try-jupyter/lab/) environment, for the purpose of showcasing QuestDB
when used in conjunction with Pandas, Jupyter, matplotlib, and other libraries.

A local ephemeral directory is created to host a Python virtual environment, plus Java 11 JRE.

To run locally:

```shell
python3 run.py
```

To run the script and edit/use the notebook from the repo's directory (to make changes to the notebook):

```shell
LOCAL_RUN=1 python3 run.py
```

## Docker

### Build image

```shell
docker build -t questdb/play:1.0.0-SNAPSHOT .
```

### Run Container

```shell
  docker run --rm \
    -p 8888:8888 \
    -p 8812:8812 \
    -p 9009:9009 \
    -p 9000:9000 \
    --name play \
    -it questdb/play:1.0.0-SNAPSHOT
```

To enter a terminal from within the image, append `bash` to the command above.

### Upload Image to Docker Hub

```shell
docker push questdb/play:1.0.0-SNAPSHOT
```

### Mount points

- **/opt/questdb/**:  QuestDB's root directory.
- **/opt/questdb/db/**:  QuestDB's data root directory.
- **/opt/backups/**: Directory for backups.
- **/opt/csv/**: Directory for backups.
- **/opt/volume0/**: Additional volume for create table, alias volume0.
- **/opt/volume1/**: Additional volume for create table, alias volume1.
- **/opt/notebooks/**: Jupyter notebooks.
- **/opt/jupyterlab.log**: Jupyter notebook log.

```shell
  docker run --rm \
    -p 8888:8888 \
    -p 8812:8812 \
    -p 9009:9009 \
    -p 9000:9000 \
    --name play \
    -v /Users/marregui/QUEST/db:/opt/questdb/db \
    -v /Users/marregui/QUEST/notebooks:/opt/notebooks \
    -v /Users/marregui/QUEST/backups:/opt/backups \
    -v /Users/marregui/QUEST/csv:/opt/csv \
    -v /Users/marregui/OTHER/volume0:/opt/volume0 \
    -v /Users/marregui/OTHER/volume1:/opt/volume1 \
    -it questdb/play:1.0-SNAPSHOT
```

### Delete image

```shell
docker rmi -f questdb/play:1.0-SNAPSHOT
docker rmi -f $(docker images -a | grep none | sed 's/  */|/g' | cut -f 3 -d'|')
```
