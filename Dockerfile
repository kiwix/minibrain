FROM python:3.14-alpine
LABEL org.opencontainers.image.source=https://github.com/kiwix/minibrain

# default location for config
ENV MIRRORBRAIN_CONFIG_FILE=/etc/mirrorbrain.conf
# run /etc/profile on shells (displays out motd)
ENV ENV="/etc/profile"
ENV VIRTUAL_ENV=/usr/local/mbenv

RUN \
    apk add --no-cache dumb-init python3 \
    rsync \
    # python dependencies
    && python3 -m venv $VIRTUAL_ENV \
    && $VIRTUAL_ENV/bin/pip3 install --no-cache-dir -U pip

# Copy pyproject.toml and its dependencies
COPY pyproject.toml README.md /src/
COPY src/minibrain/__about__.py /src/src/minibrain/__about__.py

# Install Python dependencies
RUN $VIRTUAL_ENV/bin/pip install --no-cache-dir /src

# Copy code + associated artifacts
COPY src /src/src
COPY *.md /src/
COPY server/conf/mirrorbrain.conf /etc/mirrorbrain.conf
COPY motd /etc/motd
COPY entrypoint.sh /usr/local/bin/entrypoint

# Install + cleanup
RUN \
    $VIRTUAL_ENV/bin/pip install --no-cache-dir /src \
    && rm -rf /src \
    && printf "\
export PATH=\"${VIRTUAL_ENV}/bin:\${PATH}\"\n\
/bin/cat /etc/motd\n\
" >> /etc/profile

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/usr/local/bin/entrypoint"]
CMD ["/bin/sh"]
