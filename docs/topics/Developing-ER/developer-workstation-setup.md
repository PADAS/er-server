# Developer Workstation Setup

## Running `das` with Visual Studio Code Remote Containers, on Mac (official/recommended method)

### Intro

This guide assumes you have already been onboarded to the engineering team, have a GitHub account and membership within the PADAS organization, you have been granted developer-level repository access, and your local development tools (git, VS Code, etc) are installed and ready to go. The bulk of this guide follows our recommended and supported approach, developing inside of remote containers, using Visual Studio Code on a Mac. If you'd like more background on remote containers, you can [review the documentation here](https://code.visualstudio.com/docs/remote/containers).

### Pre-Requisites

- [Visual Studio Code (VSCode)](https://code.visualstudio.com/)
- Python 3.10 - python 3.10 is what our ER server runs on. You may opt to use a newer version locally yourself.
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and/or [GitHub CLI](https://cli.github.com/)
- make (`xcode-select --install` or `brew install make`) _for OSX users._
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- GEOS (`brew install geos`) _in case of running native_
- pre-commit (`brew install pre-commit`)

### Steps

1. Create a local directory on your machine to put ER source code. Then **clone our server and web client repositories**:
   1. https://github.com/PADAS/das
   2. https://github.com/PADAS/das-web-react

2. **Configure Docker Desktop** with what RAM, CPU and disk space you have to spare. I gave it 8 cpus, 8 gb ram and 50 gb disk space. (optional, you can use the command line option if your OS has it)

3. **Set up your local environment's runtime settings** by following the instructions in the [Server Settings](#server-settings) section.

4. **Set up your pre-commit hooks** by following the instructions in the [Pre-commit hooks](#set-up-pre-commit-hooks) section.

5. Run `make start` from the root of `das` to **spin up docker containers for Postgres and Redis**.
   - This step has to be **run on your local machine, not inside the remote container** environment
   - If these containers get torn down for any reason, **you'll have to run this step again** to continue working with `das`
   - Troubleshooting connecting to the postgres db from ER server project: We have seen depending on the postgres image used, the database server is not configured to allow password method connections. Review the pg_hba.conf by hand in that case. We want to ensure the postgres server is configured to allow password authentication method.
     - Add this line or similar:
       ```
       host all all 127.0.0.1/32 password
       ```
     - Then execute this in psql to reload the pg_hba.conf file:
       ```sql
       SELECT pg_reload_conf();
       ```

6. **Set up VSCode extensions**
   1. Install Python extensions to your liking
   2. Install the [Remote Containers extension pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

7. **Restart VSCode** and open the `das` project

8. VS Code should now prompt you to **open the project in a remote container** (see toast messages at the bottom right of your screen). Click the link in the notification to do so.
   - You can also **manually trigger this action** by using key command **Cmd+Shift+P**, then selecting "_Remote-Containers: Open Folder in Container_" from the dropdown menu.

9. **Building the container will take a while** as it installs Ubuntu and its other dependencies. Once complete, your development environment is nearly set up and you are provided with a bash shell inside the remote container, from which to issue development and management commands.

10. Now you are ready to **migrate the db**.
    - Use the **VSCode launch task** `Django migrate db`
    - VSCode launch tasks can be found near the top left of the "run and debug" section (where it says "Django:Run").

11. After the migrations complete, we want to **install the necessary data fixtures for a new EarthRanger instance** (event types, maps, permission sets and a default admin). **You only need to do this once** after installing a new database.
    1. First use the **VSCode launch task** `Django initial data`
    2. Optional: set up a second tenant in your local. This is an advanced configuration.
       - Use the **VSCode launch task** `New tenant initial data`
       - **A prompt will appear when you select this task**. Type in the hostname from your .env file (which should be `localhost` unless you're doing something fancy) and hit Return.

12. **Set up PyTest** so you can **test your code as you develop**.
    1. Use the **VSCode launch task** `PyTest --createdb`
    2. Once complete, run your tests by using the **VSCode launch task** `PyTest`

13. **Run the application**
    - You made it! Now it's time to run `das`. Choose one of these options from the launch settings in VSCode in the "run and debug" panel:
      - **Django:Run** - stand up the API server using runserver
      - **Django:Gunicorn** - similar to Django:Run, but uses the Gunicorn server instead
      - **Django:GunicornRT** - Run the API stack and the realtime services. **Only use this when you need to debug the realtime services alongside the API.**
      - **ER Workers** - runs the celery worker that pulls jobs from all of our celery queues. In production we break this up into three workers, but for simplicity here, we only run one worker with several threads
      - **Django:MQL** - this is our pubsub service. Facilitates message passing between services.
      - **Django dumpdata** - This runs the _dumpdata_ management command
    - **To run the complete stack, launch these three tasks.** _You should rarely need to do this._
      1. Django:GunicornRT
      2. ER Workers
      3. Django:MQL

#### Additional Information

- If you manually set up your own database server, configure like this after logging in using psql:
  ```sql
  CREATE ROLE das WITH LOGIN SUPERUSER PASSWORD 'password';
  CREATE DATABASE das ENCODING utf8 owner das;
  \c das
  CREATE EXTENSION IF NOT EXISTS "postgis";
  ```

- If you plan on using VSCode-integrated source control tools, update your Git config inside the container:
  ```bash
  git config --global user.email "<email>@earthranger.com"
  git config --global user.name "<your name>"
  ```

---

## Server Settings

System settings in `das` are defined by two mechanisms:

1. **The Django settings system**, which defines the baseline system settings
   - This includes a series of `settings.py` files and an `.env` file, which you must create when setting up your local environment.

2. **The Tenant Management Service (TMS)**, which augments individual sites with their specific settings.
   - This is preloaded for local development using fixtures generated during the `loaddata` phase of local developer installation. You don't have to run the TMS locally.

### Override settings using ".env" file

**You must create your .env file.** Copy the `.env.template` file from `das` into `das/das` and rename it to `.env`.

**Modify that `.env` as needed**, such as changing the FQDN to wherever you run your server (typically `localhost`). Most of the defaults from `.env.template` should be correct for an out-of-the-box setup following this guide.

**Ensure these values are in your .env file:**

```bash
DB_PASSWORD=das
GEOS_LIBRARY_PATH= #one of these VALUES:
# /usr/lib/x86_64-linux-gnu/libgeos_c.so.1 IF YOU ARE ON AN X86_64 ARCHITECTURE CHIP
# /usr/lib/aarch64-linux-gnu/libgeos_c.so.1 IF YOU ARE ON AN ARM ARCHITECTURE CHIP
```

```bash
# hint, when running on an ARM system the GEOS path would be
# GEOS_LIBRARY_PATH='/usr/lib/aarch64-linux-gnu/libgeos_c.so.1'
```

```bash
FQDN=localhost # unless you've configured your host otherwise
# without TMS, we load tenant settings from local data.
# comment out TMS_API_CLIENT and TENANT_ID if you have TMS configured
TMS_API_CLIENT="core.tms.DjangoSettingsClient"
# develop.pamdas.org tenant id
TENANT_ID="28bf3d60-195f-41c7-ad75-d249d4d32430"
```

```bash
MEMORY_STORE_CLIENT="utils.persistent.RedisStorage"
MEMORY_STORE_HOST="host.docker.internal" #this connects to the local redis container instead of the TMS Memorystore redis instance used in production deployments
MEMORY_STORE_PORT=6379
MEMORY_STORE_DATABASE=4
```

```bash
GITGUARDIAN_API_KEY="<your key here>" # the API key from your GitGuardian account when you set up your pre-commit hooks
GITGUARDIAN_DOTENV_PATH=/workspaces/das/das/.env # set a shell environment variable for the pre-commit ggshield library to find
```

Our advanced local development setup has pgcat configured. If you decide to simplify things, add the following to your .env file, to instruct our Django settings to use the simple brew installed postgresql server.

```bash
DB_POOLER_NAME=das
DB_POOLER_HOST=host.docker.internal
DB_POOLER_PORT=5432
```

_For environments outside OSX:_

```bash
DB_HOST=postgis
MEMORY_STORE_HOST="redis"
REDIS_HOST="redis"
```

**Extra info about how our Django settings work:**

The primary Django settings exist in the das_server app (`das/das/das_server`), which is the project's root Django app.

- `das_server/settings.py` - primary settings file. It contains default settings, and additionally loads environment variables to update some defaults.
- `das_server/local_settings_docker.py` - these inherit from `settings.py`. This django_settings_module is used in our kubernetes pod deployments. Kubernetes secrets and configmap is used to inject environment variables into the running pods.
- `test_scripts/unittest_settings.py` - used by our CI unit test runner in CircleCI, executing in a `docker compose`-built environment. This settings file inherits from local_settings_docker, loading environment variables and overriding a few settings in this file.

**To avoid mixing up settings between development and testing environments, use the VSCode launch tasks** available for running pieces of the stack in development and testing modes.

---

## Set up pre-commit hooks

1. **Install pre-commit libraries and establish the git hooks:** `pre-commit install`
   - To manually run pre-commit: `pre-commit run --all-files`
   - To update pre-commit: `pre-commit autoupdate`

2. **Install GitGuardian (GG)** [by following this documentation](https://docs.gitguardian.com/ggshield-docs/getting-started) to detect secrets before they are pushed.
   - Once installed, authorize ggshield by running `ggshield auth login`
     - You will have to set up a GG account if you don't have one already.
     - In addition to a pre-commit hook for GG, you can manually trigger a repo scan at any time by executing this command: `ggshield secret scan repo /path/to/your/repo`
     - Add the appropriate GG variable values to the `.env` file as described in the [Server Settings](#server-settings) section.

## Run Redis and Database in containers

The project has a `Makefile` in the root directory with a single task:

- **start**: _Start storage containers (`redis` and `postgres`)_

Run with: `make start` at project root directory.

## Daily development task examples

### I finish my changes, want to run new/existing unit tests

- If it is the first time running unit tests through VSCode, you **must** first run the VSCode task: `PyTest --createdb`. This will create a new database called `test_das` to be used in future tests and avoid the creation of a db every time. (Remember to run this task again if you made changes with migrations.)
- Run `PyTest` - this launches a prompt to write your desired path of test. If you want to hard code the path for a while, just click on the gear next to the task and change the last line in `args` property and overwrite `${input:pytest_path_args}` with your desired path (don't commit the file `launch.json`).

### I want to run a manage.py command

You have two options:

1. Run `Django manage command` task and write the command in the prompt
2. If your command has arguments or something special, edit `Django manage command` - click on the gear next to the name and overwrite the `args` property:
   ```json
   "args": [
       "${input:django_command}",
       "${input:django_command_args}"
   ],
   ```
   with your desired command:
   ```json
   "args": [
       "makemigrations", "activity", "--empty"
   ],
   ```
   _Remember to not commit `launch.json` changes._

## I want to use another text editor

### PyCharm

Francisco helped set up PyCharm and can help you too.

### Neovim

Arthur and Francisco are neovim users and have successfully set up the project to work with neovim using the devcontainer and devpod.

---

## Mac Native Install (alternative to devcontainer)

Here we are running the das project on bare metal, rather than in a docker container. Prepare for some fiddling to get the project running. This is not recommended for a straightforward install. Prefer using the docker approach in VS Code.

### 1. Install Brew

Brew makes it easy to install the necessary libraries to run the ER stack locally. [Download brew here.](https://docs.brew.sh/Installation)

### 2. Install Python 3.10 in a venv using uv

1. `brew install uv`
2. `cd das` (into the directory you cloned the das repo)
3. `uv venv --python=3.10 .venv`
4. `source .venv/bin/activate`
5. Notes: be sure there is no `.python-version` file in the root directory

### 3. Install GDAL, libproj and geos

```bash
brew install gdal
brew install proj
brew install geos
```

### 4. Install Project Dependencies

Use uv to install the requirements. Requirements are found in `pyproject.toml`, and are pinned in `uv.lock`.

```bash
uv sync --group dev
```

### 5. Set GEOS Path in .env

See the [Server Settings](#server-settings) section on your local .env file.

### Other Mac Utilities

- [oh my zsh](https://ohmyz.sh/) - handy utility for managing your zsh
