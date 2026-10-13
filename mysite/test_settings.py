"""Test-only settings that override the default DATABASE to an in-memory SQLite.

Purpose: allow `python manage.py test --settings=mysite.test_settings` to run the
test suite WITHOUT touching the live MySQL database (no test tables are created
in MySQL, no records are inserted/updated/deleted there). Everything stays in a
throwaway in-memory SQLite database that vanishes when the runner exits.

The models for this project are all declared with ``managed = False``, so the
new Stage-1 tests are purely introspective (they never query the database).
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}