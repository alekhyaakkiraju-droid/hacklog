==================
What is Hacklog?
==================

Hacklog is a security software that detects compromised user accounts 
by applying statistical analysis to service access logs.

Hacklog is implemented as a system deamon that accepts log stream via syslog 
protocol.


http://dandb.github.io/hacklog/

Development
============

[![CI](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml/badge.svg)](https://github.com/alekhyaakkiraju-droid/hacklog/actions/workflows/ci.yml)

Clone repository and install the project
```
git clone git@github.com:alekhyaakkiraju-droid/hacklog.git
cd hacklog
pip install -e ".[test,dev]"
pytest tests/
```

### Branch protection

Configure the following rules on `main` / `master` / `release-next` in GitHub repository settings (**Settings → Branches → Add rule**):

- Require a pull request before merging
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Required status check: **CI / quality (3.12)** and **CI / quality (3.13)**

This ensures ruff, black, isort, mypy, bandit, and pytest all pass before merge.

Start software
```
cd hacklog/hacklog
./start.sh  # start service
./stop.sh   # stop  service
```

Deployment
==========

Install hacklog package
``yum -y install hacklog``

Start the service 
``service hacklog start``

Point to your syslog output to ``@<hacklog server>``


Community
=========

Mailing list

https://groups.google.com/forum/#!forum/hacklog-devel

https://groups.google.com/forum/#!forum/hacklog-users

Chat 
[![Gitter](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/dandb/hacklog?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
