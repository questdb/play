## Docker

### Build image
docker build -t io.questdb.play:1.0-SNAPSHOT .

### Build container

docker run --rm -p 8888:8888 -p 8812:8812 -p 9009:9009 -p 9000:9000 --name questdb-play -it io.questdb.play:1.0-SNAPSHOT
docker run --rm --network host --name questdb-play -it io.questdb.play:1.0-SNAPSHOT bash

### Delete image

docker rmi -f io.questdb.play:1.0-SNAPSHOT
docker rmi -f $(docker images -a | grep none | sed 's/  */|/g' | cut -f 3 -d'|')

### Prune system

docker system prune
