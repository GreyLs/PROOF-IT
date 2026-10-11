FROM caddy:2.11.7-alpine
RUN mkdir -p /data /config && chown -R 10004:10004 /data /config
USER 10004:10004
