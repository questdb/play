#
#     ___                  _   ____  ____
#    / _ \ _   _  ___  ___| |_|  _ \| __ )
#   | | | | | | |/ _ \/ __| __| | | |  _ \
#   | |_| | |_| |  __/\__ \ |_| |_| | |_) |
#    \__\_\\__,_|\___||___/\__|____/|____/
#
#  Copyright (c) 2014-2019 Appsicle
#  Copyright (c) 2019-2023 QuestDB
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

FROM python:3.10.9-slim-buster

EXPOSE 8888/tcp
EXPOSE 8812/tcp
EXPOSE 9000/tcp
EXPOSE 9009/tcp

ENV QUESTDB_TAG=6.7
ENV ARCHITECTURE=x64
ENV PYTHONUNBUFFERED 1
ENV VIRTUAL_ENV=/opt/venv
ENV JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$JAVA_HOME/bin:$VIRTUAL_ENV/bin:$PATH"

# Update system
RUN apt-get -y update
RUN apt-get -y upgrade
RUN apt-get -y --no-install-recommends install syslog-ng ca-certificates git curl wget gnupg2 lsb-release software-properties-common unzip iputils-ping

# Install JDK
RUN wget -O- https://apt.corretto.aws/corretto.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/winehq.gpg >/dev/null && \
    add-apt-repository 'deb https://apt.corretto.aws stable main' && \
    apt-get update && \
    apt-get install -y java-17-amazon-corretto-jdk=1:17.0.3.6-1

RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/*

# Install QuestDB
WORKDIR /opt
RUN echo tag_name ${QUESTDB_TAG}
RUN curl -L -o questdb.tar.gz "https://github.com/questdb/questdb/releases/download/${QUESTDB_TAG}/questdb-${QUESTDB_TAG}-no-jre-bin.tar.gz"
RUN tar xvfz questdb.tar.gz
RUN rm questdb.tar.gz
RUN mv "questdb-${QUESTDB_TAG}-no-jre-bin" questdb

# Virtual env
RUN python3 -m venv $VIRTUAL_ENV
COPY requirements.txt .
RUN pip install --no-compile --only-binary :all: -r requirements.txt

# Aliases
RUN echo 'alias l="ls -l"' >> ~/.bashrc
RUN echo 'alias ll="ls -la"' >> ~/.bashrc
RUN echo 'alias rm="rm -i"' >> ~/.bashrc

# Run script
COPY notebooks notebooks
COPY run.py .
CMD ["/opt/venv/bin/python3", "run.py", "IN_DOCKER"]
