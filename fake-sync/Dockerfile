FROM python:3.14-alpine
LABEL org.opencontainers.image.source="https://github.com/kiwix/minibrain"

RUN \
    apk add --no-cache dumb-init rsync \
    && python3 -m pip install rich==15.0.0 humanfriendly==10.0

COPY sparse-sync.py /usr/local/bin/sparse-sync
COPY forever-entrypoint.py /usr/local/bin/entrypoint

ENV SLEEP_DURATION="30"
ENV ENTRYPOINT_DEBUG=""

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/usr/local/bin/entrypoint"]
CMD ["sparse-sync", "--help"]

