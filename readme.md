# EarthRanger Server aka DAS

## EarthRanger
EarthRanger is a software solution that aids protected area managers, ecologists, and wildlife biologists in making more informed operational decisions for wildlife conservation.

For more information on the EarthRanger program, visit [EarthRanger](https://earthranger.com)


## Software
This repository contains the code that makes up the EarthRanger web services API.

ER Server is built on the Django web framework and uses PostgreSQL as the data storage backend.

## Developing

### Visual Studio Code Remote Containers
We recommend developing ER Server using VS Code. We have documented setting up Code and provided the docker configuration to run in remote containers.

In this setup, we require Docker Desktop to be installed, in which we build an image to run pieces of the EarthRanger server stack. This is a do-it-yourself setup to allow you to debug each service in the stack as you need. To simplify setup, we recommend installing PostgreSQL/PostGIS and Redis using Brew which you can then point the Django ER system at. Once PostgreSQL is installed follow these [steps](#local-postgresql-db-setup) to configure the db. If you are comfortable with docker, you could alternatively run PostgreSQL and Redis there as well. Review the details [here on Remote Containers](https://code.visualstudio.com/docs/remote/containers) if you want more background on it.

1. Install Docker Desktop and configure it with what RAM, CPU and disk space you have to spare. I gave it 8 cpus, 8 gb ram and 50 gb disk space.

2. Install Visual Studio Code with the python extensions.

3. Install the [Remote Containers extension pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

4. At this point, restart VS Code and open the das project

5. VS Code should now prompt you to open the open the project in a remote container, otherwise cmd-shift-p and select “Remote-Containers: Open Folder in Container”

6. This will take a while to build the container, installing all the Ubuntu packages in the process

7. Once complete you now have a full dev environment complete with bash shell to execute django manage commands

8. Setup “local_settings.py” in the das/das_server directory. Make a copy of local_settings.template into local_settings.py. In this update the location of redis and the db.

9. Also look in the local_settings file for the name of the db, so that you can configure your postgresql with a new db of that name as well as a user account with read/write access to same db.

10. Now you are ready to migrate the db. Get a shell in vs code, goto das, the directory where manage.py is located.

11. execute > python3 manage.py migrate

12. at which point if all went well, we see Django migrations being applied.

13. Post migration we want to install event types, maps, permission sets and a default admin. We do that manually with the loaddata management command. You only need to do this once after installing a new database.

14. Execute > python3 manage.py loaddata initial_admin initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model

### Local PostgreSQL db setup
Run PostgreSQL with PostGIS on your local system. On a mac we use brew to install.
```
brew install postgresql

brew install postgis

brew services start postgresql
```
Then once PostgreSQL is running, setup the user our django server will use, along with creating the database.
```
createuser -s das
createdb -U das das --encoding='utf8'
psql -U das -c "ALTER USER das WITH PASSWORD 'password';"
```
Once the db has been created and the server is able to run, you will want to migrate the db using the “python3 manage.py migrate” command


### Python Coding Conventions
PEP 8 -- Style Guide for Python Code

Spaces not tabs, 4 space indents

Maximum line length less than 80

Doc strings less than 72

Line breaks before operators

Here is a biased view of using [PEP8](https://pep8.org/)

### Comments and Documentation
We use the Google standard for docstring generation for functions and classes. Docstrings are explored in depth here in [PEP0257](https://www.python.org/dev/peps/pep-0257/)

VSCode has a recommended docstring generator which can be found [here](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring)

### Python Type Hints
As supported since python 3.5, we can now annotate our code to express types for all function arguments, return values and more generally data structures. This is not enforced at run-time, but most modern IDEs with python extensions can warn when types are crossed.

It is recommended that new code expresses types. See [type hints](https://docs.python.org/3.7/library/typing.html)

### Managing python requirements
We use pip-tools tools to manage our requirements so that project and all dependent python packages are pinned to a specific version.

The canonical list of packages required for the project are contained in dependencies/requirements.in Pinned github commit references are kept in requirements-pinned.txt

run the following command to prepare a pinned set of dependencies for the app

pip-compile requirements.in

run this command to update versions:

pip-compile --upgrade

To install requirements using pip

pip install -r requirements.txt -r requirements-pinned.txt --find-links ./wheelhouse


### Secrets, Tokens, Passwords
We are using Yelp supported [detect-secrets project](https://github.com/Yelp/detect-secrets) to find secrets or passwords we mave have inadvertantly left in our code.

The base file is secrets.baseline
We generated it by executing:
```
detect-secrets scan > secrets.baseline
```

Once the baseline was set, we then execute the following to look for secrets in all checked in code:
```
git ls-files -z | xargs -0 detect-secrets-hook --baseline secrets.baseline
```

Auditing the baseline file by executing
```
detect-secrets audit secrets.baseline
```
