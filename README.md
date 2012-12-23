# LNLDB 

## Intro

Requirements are in reqs.txt

```
pip install -r reqs.txt
```

modify settings.py to your database spec

```
python manage.py syncdb
````

## Notes

DB migrations are handled by south
Default groups are in groups.json, import with 

```
python manage.py loaddata groups.json
```

All WPI specific code hasn't been grafted on yet...
All views have their functionality written out in """ """
