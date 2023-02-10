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
ENV JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
ENV PATH="$JAVA_HOME/bin:${PATH}"

# Update system
RUN apt-get -y update
RUN apt-get -y upgrade
RUN apt-get -y --no-install-recommends install syslog-ng ca-certificates git curl wget vim procps gnupg2 lsb-release software-properties-common unzip less tar gzip iputils-ping

# Install JDK
RUN wget -O- https://apt.corretto.aws/corretto.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/winehq.gpg >/dev/null && \
    add-apt-repository 'deb https://apt.corretto.aws stable main' && \
    apt-get update && \
    apt-get install -y java-17-amazon-corretto-jdk=1:17.0.3.6-1

# Clean after packages installation
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/*

# Aliases
RUN echo "alias l='ls -l'" >> ~/.bashrc
RUN echo "alias ll='ls -la'" >> ~/.bashrc
RUN echo "alias rm='rm -i'" >> ~/.bashrc

WORKDIR /opt

# Install QuestDB
RUN echo tag_name ${QUESTDB_TAG}
RUN curl -L -o questdb.tar.gz "https://github.com/questdb/questdb/releases/download/${QUESTDB_TAG}/questdb-${QUESTDB_TAG}-no-jre-bin.tar.gz"
RUN tar xvfz questdb.tar.gz
RUN rm questdb.tar.gz
RUN mv "questdb-${QUESTDB_TAG}-no-jre-bin" questdb

# Configure QuestDB
RUN ulimit -S unlimited
RUN ulimit -H unlimited
RUN mkdir csv
RUN mkdir tmp
RUN mkdir backups
RUN mkdir questdb/db
RUN mkdir questdb/conf
RUN echo "config.validation.strict=true" > questdb/conf/server.conf
RUN echo "query.timeout.sec=120" >> questdb/conf/server.conf
RUN echo "cairo.sql.copy.root=/opt/csv" >> questdb/conf/server.conf
RUN echo "cairo.sql.copy.work.root=/opt/tmp" >> questdb/conf/server.conf
RUN echo "cairo.sql.backup.root=/opt/backups" >> questdb/conf/server.conf

# Install requirements.txt
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-compile --only-binary :all: -r requirements.txt
RUN jupyter-lab --generate-config && sed -i -e "s|# c.ServerApp.allow_remote_access = False|# c.ServerApp.allow_remote_access = True|g" /root/.jupyter/jupyter_lab_config.py

COPY notebooks notebooks
COPY run.py run.py
COPY docker_run.py docker_run.py
RUN chmod +x docker_run.py
CMD ["/opt/docker_run.py"]
