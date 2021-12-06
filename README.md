# Captivise

## Setup project

### Django

The steps below will get you up and running with a local development environment. We assume you have the following installed:

- python (3.5)
- pip
- virtualenv

First make sure to create and activate a virtualenv, then open a terminal at the project root and install the requirements for local development::

```bash
    pip install -r requirements.txt
```

Symlink settings_local.py::

```bash
    ln -s environments/dev/settings_local.py config/settings_local.py
```

Create a local database::

```sql
    CREATE DATABASE captivise;
```

Run `migrate` on your new database::

```bash
    python manage.py migrate
```

You can now run the `runserver` command::

```bash
    python manage.py runserver
```

Open up your browser to http://127.0.0.1:8000/ to see the site running locally.

### Bower

We assume you have the following installed:

- node (5.5)
- npm (3.5.3)

To install bower:

```bash
    npm install
```

To install the bower components:

```bash
    npm run bower:install
```

### Gulp

Use `gulp` to compile the styles for the project.

To build the styles:

```bash
    npm run gulp:build
```

To automatically compile when changes are made:

```bash
    npm run gulp:watch
```

## Running Celery

Celery is responsible for handling asynchronous tasks. When developing, you can run it with:

```bash
    celery worker -A config -l INFO -B
```
