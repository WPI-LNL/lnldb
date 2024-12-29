# LNLDB
[![Django CI](https://github.com/WPI-LNL/lnldb/actions/workflows/django-ci.yml/badge.svg)](https://github.com/WPI-LNL/lnldb/actions/workflows/django-ci.yml) [![Coverage Status](https://coveralls.io/repos/WPI-LNL/lnldb/badge.svg?branch=master&service=github)](https://coveralls.io/github/WPI-LNL/lnldb?branch=master) [![Documentation](https://readthedocs.org/projects/lnldb/badge/?version=latest&style=flat)](https://lnldb.readthedocs.io/en/latest/)

## Intro
LNLDB now runs under Python3.12 and Django 4.2 or later.

## To Install (Testing)
##### Install required system packages
You are going to need some basic Python/Git tools to run the code. The most important are Python3 and virtualenv (which allows you to install python libs without root). The rest are to compile the python binary libraries, namely MySQL and image manipulation.

###### Linux:
```
sudo apt-get install python3 python3-dev python-pip python-virtualenv git libtiff5-dev libjpeg8-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev libmysqlclient-dev
```

###### macOS:
```
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
pip install virtualenv
```

It is certainly possible to run via Windows practically without changes, but figuring out that setup is left as an
excercise for the user (hint: use pycharm).

##### Get the sources
If you're reading this outside of Github, you can skip this.

```
git clone https://github.com/WPI-LNL/lnldb.git
cd lnldb
```

##### Install Python packages
This uses a lot of library functionalities in the form of plugins. We will make a virtualenv to keep all of this away
from the system Python installation (ie. don't need root), and install our packages directly to the `env` folder.

```
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

##### Initialize the database
The first line makes/loads the actual database schema, by walking through all of the previous schemas and making necessary
changes to the database one-by-one so that no data is ever lost regardless of versions. On your machine, the database
will by default be an Sqlite file in the runtime folder, on the server, it's WPI's hosted MySQL server.

The second line will populate any data with a useful initial value. Examples include groups, permissions, locations, etc.
If you have updated these or have existing data, don't run this.  You can also use this method to load a backup from the
production database (`dbbak` on server).

The third will create an account to let you log in once you've started the server.
```
python manage.py migrate
python manage.py loaddata fixtures/*.json
python manage.py createsuperuser
```

##### Run the tests

This app includes a number of self-checks to sanity test new code. All new patches are expected to have
tests included, and will be checked automatically when pushed to Github. Also try using the '-n' flag to speed it up.

```
python manage.py test
```

##### Run it!
`python manage.py runserver` or `python manage.py shell_plus`
Note that in future sessions, you must first call `source env/bin/activate` to set enter your Python virtual environment.

## Notes

- All server-specific keys, directories, etc. haven't and won't be included. The app checks for a file at
    `lnldb/local_settings.py`, where those and any platform-specific options can be included.

## Server Notes
- To update static files from the apps to the webserver directory, run `python manage.py collectstatic`
-  django-saml2-auth requires the Linux packages `xmlsec1` and `xmlsec1-openssl` to be installed on the host

