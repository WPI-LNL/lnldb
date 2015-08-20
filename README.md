# LNLDB 
[![Build Status](https://travis-ci.org/WPI-LNL/lnldb.svg)](https://travis-ci.org/WPI-LNL/lnldb) [![Coverage Status](https://coveralls.io/repos/WPI-LNL/lnldb/badge.svg?branch=master&service=github)](https://coveralls.io/github/WPI-LNL/lnldb?branch=master) [![Dependency Status](https://gemnasium.com/WPI-LNL/lnldb.svg)](https://gemnasium.com/WPI-LNL/lnldb)

## Intro
LNLDB runs under Python2.x and Django.

## To Install (Testing)
##### Install required system packages (by reference of a barebones Debian build; adjust for your system)
```
sudo apt-get install python2.7 python2.7-dev python-pip git
```

##### Get the sources
```
git clone https://github.com/WPI-LNL/lnldb.git
cd lnldb
```

##### Install Python packages
```
sudo pip install -r requirements.txt
```

##### (Optional) Create a local_settings.py with your settings
Take the pieces of lnldb/settings.py that need to change and put it in lnldb/local_settings.py. 
That makes it easy to spawn a local copy without messing with other coders' settings.  The default
settings.py may work for you.

##### Initialize the database
```
python manage.py migrate
python manage.py loaddata groups.json
python manage.py loaddata categories.json
````

##### Run it!
```
python manage.py runserver
```


## Notes

- All server-specific keys, directories, etc. haven't and won't be included. That's what 
local_settings.py is for.

- Changes that actually change code should be put as pull requests, so that CI can test them. 
Currently not much is tested (mainly public views), but passing those tests, putting your own 
tests on non-trivial code (5%), and a subset of PEP8 are automatically enforced. See .travis.yml.

- Currently, the initial fixtures are a little lacking. If you get an error saying a certain object
is not found, create it in the admin.
