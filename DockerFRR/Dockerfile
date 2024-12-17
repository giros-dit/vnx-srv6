FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    net-tools \
    iputils-ping \
    lsb-release

RUN wget https://deb.frrouting.org/frr/keys.asc && \
    apt-key add keys.asc && \
    rm keys.asc

RUN release=$(lsb_release -s -c) && \
    echo "deb https://deb.frrouting.org/frr $release frr-stable" >> /etc/apt/sources.list

RUN apt-get update && apt-get install -y \
    frr \
    frr-pythontools

RUN echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf && \
    echo "net.ipv6.conf.default.seg6_enabled=1" >> /etc/sysctl.conf &&\
    echo "net.ipv6.conf.all.seg6_enabled=1" >> /etc/sysctl.conf