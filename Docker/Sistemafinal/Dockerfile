FROM wbitt/network-multitool:latest

RUN apk update && \
    apk add --no-cache iperf3 && \
    rm -rf /var/cache/apk/*

EXPOSE 5201