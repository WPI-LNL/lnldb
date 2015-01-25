# LNLDB 

## Intro
LNLDB runs under Python2.x and Django.

## To Install (Testing)
1. Install required system packages (by reference of a barebones Debian build; adjust for your system)
```
sudo apt-get install python2.7 python2.7-dev python-pip git mysql-server
```

2. Get the sources
```
git clone https://github.com/jmerdich/lnldb.git
cd lnldb
```

2. Install Python packages
```
sudo pip install -r reqs.txt
```

3. Setup your database
```
mysql -u root -p
CREATE DATABASE lnlsql;
GRANT ALL PRIVILEGES ON lnlsql.* TO lnl@localhost IDENTIFIED BY 'password';
exit;
```

4. Create a local_settings.py with your settings
Take the pieces of lnldb/settings.py that need to change and put it in lnldb/local_settings.py. 
That makes it easy to spawn a local copy without messing with other coders' settings. 

5. Initialize the database
```
python manage.py syncdb
python manage.py migrate
python manage.py loaddata groups.json
python manage.py loaddata categories.json
````

## Notes

DB migrations are handled by south


All WPI specific code hasn't been grafted on yet...
All views have their functionality written out in """ """
