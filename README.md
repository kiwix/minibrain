# minibrain

Minimalist Mirrorbain maintenance tools for Kiwix Load-balancer


## Setup

```sh
# start postgres container, supplying db name, user and pass
# Database and roles will be created if DB does not exists
podman run --rm --name postgres -p 5432:5432 \
    -v $(PWD)/data:/var/lib/postgresql/18/docker:rw \
    -e POSTGRES_USER=mirrorbrain \
    -e POSTGRES_DATABASE=mirrorbrain \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    -it docker.io/library/postgres:18.4

# load the schema into the DB (first time)
podman cp server/sql/schema.sql postgres:/tmp/
podman exec -it postgres /bin/sh -c 'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /tmp/schema.sql'

# load some initial data (country, region, version)
podman cp server/sql/initialdata.sql postgres:/tmp/
podman exec -it postgres /bin/sh -c 'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /tmp/initialdata.sql'
```
