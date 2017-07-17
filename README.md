# LNLDB
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy) [![Build Status](https://travis-ci.org/WPI-LNL/lnldb.svg)](https://travis-ci.org/WPI-LNL/lnldb) [![Coverage Status](https://coveralls.io/repos/WPI-LNL/lnldb/badge.svg?branch=master&service=github)](https://coveralls.io/github/WPI-LNL/lnldb?branch=master)
## Intro
LNLDB runs under Python2.x and Django.

## To Install (Testing)
##### Install required system packages
You are going to need some basic Python/Git tools to run the code. The most important are python2 (not 3) and virtualenv (which allows you to install python libs without root). The rest are to compile the python binary libraries, namely MySQL and image manipulation. 

```
sudo apt-get install python2.7 python2.7-dev python-pip python-virtualenv git libtiff5-dev libjpeg8-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev libmysqlclient-dev
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
virtualenv --python=python2.7 env
source env/bin/activate
pip install -r requirements_debug.txt
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

##### (Optional) Run the tests

This app includes a number of self-checks to sanity test new code. All new patches are highly recommended to have
tests included, and will be checked automatically when pushed to Github. Also try using the '-n' flag to speed it up.

```
python manage.py test
```

##### Run it!
`python manage.py runserver` or `python manage.py shell_plus`
Note that in future sessions, you must first call `source env/bin/activate` to set up the local path

## Notes

- All server-specific keys, directories, etc. haven't and won't be included. The app checks for a file at
    `lnldb/local_settings.py`, where those and any platform-specific options can be included.
