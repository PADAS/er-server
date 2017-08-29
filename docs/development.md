## Development Standards and Information

### OnBoarding

#### Source Code ####

Find the source code repositories on GitHub\. Ask project lead to add you to the list of users\.

The Github organization is Padas: [https://github\.com/padas](https://github\.com/padas)

create a local directory on your machine to put the code repos for DAS\. Clone the das server and web repos\.

[https://github\.com/PADAS/das](https://github\.com/PADAS/das)

[https://github\.com/PADAS/das\-web](https://github\.com/PADAS/das\-web)

#### Development Environment Setup

##### Development Tools to install

Depending on the platform you develop code on, here are some instructions\. If you are hard core, you could just get the source code, write code using VIM and deploy into your local docker\.

__Windows__

Using Windows for development takes some work to setup support for Docker as well as the tools\. You will need to be running the Windows 10 creators edition and have the Linux Subsystem for Windows installed which gives you access to an Ubuntu 16\.04 bash shell and most of it's tools\. We will be installing the docker client tools in this linux subsystem which will then access the running docker server over local port 2375\.

1. Install Docker for Windows, Edge version. Be sure you install the [Edge](https://docs.docker.com/docker-for-windows/install/)^[https://docs.docker.com/docker-for-windows/install/] version. 

2. Adjust the settings in Docker for Windows to "Expose daemon on tcp:..."

3. Enable Shared Drives in Docker for Windows so that we can mount or code in the containers.

4. Install Linux subsystem for Windows by following this [guide](https://msdn.microsoft.com/en-us/commandline/wsl/install_guide)^[https://msdn.microsoft.com/en-us/commandline/wsl/install_guide].

__Mac__

The first requirement is to install suitable versions of GDAL, LibProj and GEOS\. Do that by following these instructions:

Download gdal complete and install it:

[http://www\.kyngchaos\.com/files/software/frameworks/GDAL\_Complete\-2\.1\.dmg](http://www\.kyngchaos\.com/files/software/frameworks/GDAL\_Complete\-2\.1\.dmg)

Once the above is installed, continue with the following commands:



> pip download GDAL==2\.1\.3

> tar \-xvzf GDAL\-2\.1\.3\.tar\.gz

> cd GDAL\-2\.1\.3\.tar\.gz

> export CFLAGS=\-Qunused\-arguments export CPPFLAGS=\-Qunused\-arguments

> python setup\.py build\_ext\\

>  \-\-gdal\-config=/Library/Frameworks/GDAL\.framework/Versions/2\.1/unix/bin/gdal\-config \\

>  \-\-library\-dirs=/Library/Frameworks/GDAL\.framework/Versions/2\.1/unix/lib/ \\

>  \-\-include\-dirs=/Library/Frameworks/GDAL\.framework/Versions/2\.1/Headers/

> python setup\.py build

> python setup\.py install

Now continue with the pip requirements found in das/dependencies

To tell Django how to find the libraries you've just installed on your Mac, you'll need to include the following in your local\_settings\.py:



> GEOS\_LIBRARY\_PATH = '/usr/local/lib/libgeos\_c\.dylib'

> GDAL\_LIBRARY\_PATH = '/usr/local/lib/libgdal\.dylib'

__Ubuntu__

##### Local Docker #####

We use docker for development and deployment\. Double check your code runs locally in Docker before pushing to the repo and subsequent staging\.

1. Install the Docker Community Edition (17.05 or greater) Be sure to install the edge version of this.

2. Install Docker Compose > 1.12


~~~~~~~
sudo bash
curl -L https://github.com/docker/compose/releases/download/1.15.0/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
~~~~~~~


3. Get your GCP credentials for our scripts to find.


~~~~~~~
cd das
./docker/keys/init.sh
~~~~~~~
If you see the following when bringing up a local pipeline, then you should re-run the above command to refresh your credentials:
ERROR: pull access denied for [gcr.io/padas-app/web/develop](http://gcr.io/padas-app/web/develop)^[http://gcr.io/padas-app/web/develop], repository does not exist or may require 'docker login'

4. To build and run with local docker contains, execute the following docker-compose command. Your local repos will be mounted in these docker containers allowing you to develop code running in docker containers.


~~~~~~~
cd das
docker-compose -f docker-compose.yml -f compose-dev.yml up -d
~~~~~~~


5. 



### Git Flow

Our source code control use is governed by the Git Flow pattern\.

Specifically we use the following naming conventions for the feature, release and hot fix branches\. In addition, the versioning system we follow is Semantic Versioning 2\.0\.0\.



##### Helpful Links #####

GitFlow: [https://datasift\.github\.io/gitflow/IntroducingGitFlow\.html](https://datasift\.github\.io/gitflow/IntroducingGitFlow\.html)

Semantic Versioning: [http://semver\.org/](http://semver\.org/)



##### Branches #####

__Feature Branches__

Feature branches are based on the current develop branch\. For feature branches, include the JIRA ticket when possible\. For example: 'feature/DAS\-1111'\. Once the feature work is completed, code is merged back into develop through a pull request on GitHub\.

version number includes the 'dev' designation for builds: 1\.15\.1\-dev\.buildnum

The version number in the develop branch should always reflect the latest version number found in either the release or hot fix branch\.

__Release Branches__

When it is time to organize a release, branch from develop at the appropriate point\. The prefix for a release is 'release/'\. A release should be numbered as well\. An example release branch name would be 'release/1\.15\.0'\. See Master Branch below for how this branch is moved into master for release\.

version number includes the 'rc' designation for builds: 1\.15\.1\-rc\.buildnum

buildnum \- reset this whenever the version number changes

__Hot Fix Branches__

Hot fix branches are based from the appropriate master tag\. Prefix a hot fix branch with 'hotfix/', for example 'hotfix/1\.15\.1'

version number includes the 'rc' designation for builds: 1\.15\.1\-rc\.buildnum

buildnum \- reset this whenever the version number changes

__Master Branch__

Once a release is ready for production release to customers, merge the release branch into master and create a tag marking the release on master\. The production build is done from this tag on the master branch\. An example tag: '1\.15\.1'

version number for the build is the same as the branch tag: 1\.15\.1

buildnum \- there is no build number for a master branch release, the version always increments\.



tag the branch and push it to the repo:
```bash
git tag -a 1.15.1 -m "release 1.15.1"
git push origin 1.15.1
```
__Support Branch__

In the case where we want to support an older software version, use a 'support' branch\. For instance Master has moved on and released code for version 1\.16\.1\. Now we need to perform some bug fixes on the 1\.15 branch\. In this instance, create a support/1\.15 branch we will use for maintaining the 1\.15 series\. The initial support branch is performed from that specific tag found on the master branch\. There is no intention to merge code fixes from the support branch into 'develop' or 'master'\.

[Examples](https://gitversion\.readthedocs\.io/en/latest/git\-branching\-strategies/gitflow\-examples/\#support\-branches)^[https://gitversion\.readthedocs\.io/en/latest/git\-branching\-strategies/gitflow\-examples/\#support\-branches] of using a support branch

version number includes the 'sup' designation for builds: 1\.15\.1\-sup\.buildnum

buildnum \- reset this whenever the version number changes

__Example workflow for a feature branch__

+ git checkout develop

+ git pull (or equivalent to be sure you have the latest code)

+ git checkout \-b feature/DAS1111

make your code changes

+ git add \<files that changed\>

+ git commit \-m "informative comment on code changes"

+ git push origin feature/DAS\-1111

once you have completed work, use the Github interface to start a Pull Request on your branch to get it merged into the 'develop' branch

delete your feature branch once it has been approved and merged into 'develop'

__Release Numbers__

Major Change 1\.x to 2\.x

The API contract is broken\. Massive changes to the codebase\.

Minor Change 1\.2 to 1\.3

New features, no major breaking changes

Micro Change 1\.2\.1 to 1\.2\.2

Bug fixes, very small features
