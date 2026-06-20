FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PERFBOX_HOME=/opt/perf-blackbox
ENV DATA_DIR=/data/perf
ENV PERF_FREQ=99
ENV WINDOW_SECONDS=60
ENV RETENTION_HOURS=24
ENV FLAMEGRAPH_DIR=/opt/perf-blackbox/FlameGraph
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    ca-certificates \
    libpython3.10 \
    libtraceevent1 \
    linux-tools-common \
    linux-tools-generic \
    perl \
    procps \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/perf-blackbox

COPY src/ /opt/perf-blackbox/src/
COPY third_party/FlameGraph/ /opt/perf-blackbox/FlameGraph/

RUN chmod +x /opt/perf-blackbox/src/bin/perfbox \
    && chmod +x /opt/perf-blackbox/FlameGraph/stackcollapse-perf.pl \
    && chmod +x /opt/perf-blackbox/FlameGraph/flamegraph.pl \
    && ln -s /opt/perf-blackbox/src/bin/perfbox /usr/local/bin/perfbox \
    && mkdir -p /data/perf /data/output /data/logs

VOLUME ["/data"]
EXPOSE 8080

ENTRYPOINT ["perfbox"]
CMD ["web", "--host", "0.0.0.0", "--port", "8080"]
