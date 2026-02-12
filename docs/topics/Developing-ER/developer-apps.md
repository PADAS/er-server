# Developer Apps

These are the apps and services we use in development of our projects.

## Miro

## GitGuardian

GitGuardian is a service that validates all commits pushed to Github, that the commit does not contain secrets. It checks after you have pushed your changes, on a post commit hook. But that's too late. We prefer you install the GitGuardian software and use it in your pre-commit hook process. See [Developer Workstation Setup](developer-workstation-setup.md#set-up-pre-commit-hooks).

We log into GitGuardian through our enterprise enabled GitHub account. This assumes you see the Enterprise Github tile for PADAS in your OKTA dashboard. Second, that IT added you to the GitGuardian OKTA group. Follow these steps to log in to GitGuardian:

1. Navigate to [their website](https://www.gitguardian.com/) and choose Login
2. On this step, select Log in with Github
3. Here, we Authorize the PADAS organization and click Continue. If the PADAS entry does not have a green check, press the Authorize button for PADAS. Then Continue.
4. At this screen, click Log in with OKTA
5. The menu in the upper left should have the AI2 project, and here is the list of open issues

## Visual Studio Code

## GitHub Copilot
