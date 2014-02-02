Hive365 IRC Bot - Python
========================

by [blha303](https://github.com/blha303)

Usage
-----

* Clone the repository
* Create a virtualenv in the repo. I use PyPy as of recently, but CPython works fine as well. `virtualenv venv`
* Get the dependencies. `venv/bin/pip install -r requirements.txt`
* Copy or move sampleconfig.yml to config.yml, edit to suit. If you get a KeyError message on starting the bot, the sampleconfig.yml may not be updated. Add the missing key to the file.
* `venv/bin/python run.py` to make sure there are no errors, then Ctrl-C and `venv/bin/twistd -y run.py` to start the daemon. Use `tail -f twistd.log` to see the log, and `kill $(cat twistd.pid)` to stop the bot. Add `-9` after `kill` if the bot is stuck in a Loop Crashed cycle.
* [Create an issue](https://github.com/blha303/H365IRC-Python/issues) if you need help.