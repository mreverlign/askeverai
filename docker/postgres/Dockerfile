FROM postgres:18-alpine

# Bake init scripts into the image so Docker Desktop bind-mount +x/noexec
# does not break shebang execution ("bad interpreter: Permission denied").
COPY initdb/ /docker-entrypoint-initdb.d/

RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/*.sh \
  && chmod a-x /docker-entrypoint-initdb.d/*.sh
