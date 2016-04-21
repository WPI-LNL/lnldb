# LNLDB 
[![Build Status](https://travis-ci.org/WPI-LNL/lnldb.svg)](https://travis-ci.org/WPI-LNL/lnldb) [![Coverage Status](https://coveralls.io/repos/WPI-LNL/lnldb/badge.svg?branch=master&service=github)](https://coveralls.io/github/WPI-LNL/lnldb?branch=master)
## Intro
LNLDB runs under Python2.x and Django.

## To Install (Testing)
##### Install required system packages 
You are going to need some basic Python/Git tools to run the code. This list is by reference of a barebones Debian/Ubuntu build. You may need to adjust for your system if you are not using that distro.
```
sudo apt-get install python2.7 python2.7-dev python-pip python-virtualenv git
```
It is certainly possible to run via Windows with only minimal changes, but figuring out that setup is left for the user.

##### Get the sources
```
git clone https://github.com/WPI-LNL/lnldb.git
cd lnldb
```

##### Install Python packages
This and most django runtimes use a lot of library functionalities in the form of plugins. We will make a virtualenv
to keep all of this away from the system Python installation, and install our packages directly to this folder
```
virtualenv --python=/usr/bin/python2 env
source env/bin/activate
pip install -r requirements.txt
```

##### (Optional) Create a local_settings.py with your settings
Take the pieces of lnldb/settings.py that need to change and put it in lnldb/local_settings.py. 
That makes it easy to spawn a local copy without messing with other coders' settings.  The default
settings.py may work for you.

##### Initialize the database
This loads the actual database schema, by literally starting back at the first revision and walking through all the 
schema changes since then. If you make a change that needs a schema update, you will need to make a new migration
(actually really easy) and run this again.
```
python manage.py migrate
```
You will also want to load in the default data.
```
python manage.py loaddata groups.json
python manage.py loaddata categories.json
````
You can also use this method to load a backup from the production database (`dbbak` on server).
```
rm runtime/lnldb.db
python manage.py migrate
python manage.py loaddata dump.json
```

##### Run it!
`python manage.py runserver` or `python manage.py shell_plus`
Note that in future sessions, you must first call `source env/bin/activate` to set up the local path

## Notes

- All server-specific keys, directories, etc. haven't and won't be included. That's what 
local_settings.py is for.

- Currently, the initial fixtures are a little lacking. If you get an error saying a certain object
is not found, create it in the admin.
