# Source Code Branching

## Modified Git Flow

Our source code control use is inspired by the Git Flow pattern.

Specifically, we use the following naming conventions for the feature, release and hot fix branches. In addition, the versioning system we follow is Semantic Versioning 2.0.0.

### PRs or how we approve code before merging

We use GitHub pull requests to solicit feedback and review of code. See below on branches for naming your branch. Once your work is ready for review, write up a pull request describing your work and any concerns. The description in the PR will also be re-purposed in our release notes.

1. Create PR from your code branch
2. Fill out the PR Description as described below, include the Jira ticket number in the title. This enables Jira to link the PR into the ticket.
3. Solicit review from appropriate developers
4. Encouraged to have a code review to share what you did and for feedback
5. Once approved and we are not in the process of preparing a release, merge the code.

#### PR Description

- Jira tickets, include description of feature or bug
- Side Effects - any potential side effects?
- Addresses issue found at site?

### Helpful Links

- GitFlow: https://datasift.github.io/gitflow/IntroducingGitFlow.html
- Semantic Versioning: http://semver.org/

### Branches

Branch names must contain DNS friendly characters as each DAS server branch can potentially be deployed as an EarthRanger site, and this is done from the branch name. That is why we can't use periods or slashes in the branch name as would be standard for GitFlow.

#### Feature Branches

Feature branches are based on the current develop branch. For feature branches, include the JIRA ticket number. For example: `ERA-1111`. Once the feature work is completed, code is merged back into develop through a pull request on GitHub.

The version number in the develop branch should always reflect one higher version number than the one found in the current release branch.

#### Release Branches

When it is time to organize a release, branch from develop at the appropriate point. A release should be numbered as well. An example release branch name would be `das-2-102-1` and for MT `release-2.102.1`.

The das server version number found in [`__init__.py`](https://github.com/PADAS/das/blob/develop/das/das_server/__init__.py) includes the `rc` designation for builds: `1.15.1-rc.buildnum`

buildnum - the buildnum is inserted by the CircleCI build process.

#### Hot Fix Branches

Hot fix branches are based from the affected release branch. Following the previous example, say a bug was identified and needed immediate fixing. We branch from `das-2-102-1`, then we follow the branch name format `ERA-2222`. The hotfix should be associated with a Jira ticket.

Once complete, the hotfix branch is merged into both the targeted release branch as well as the develop branch.

**Hot fix operations:**

1. From the release branch `das-2-102-1`, create a hotfix branch named for the Jira Ticket `ERA-2222`
2. Make the changes necessary to the ERA-2222 branch to address the bug. Hint: create a failing unittest where possible, then fix the bug.
3. Create the PR and follow a high priority review process, involving QA
4. Once approved, merge the fix into the release branch.
5. Create a PR to merge the release branch into `develop`. See the PR reviewed and merged.

#### Main Branch

_This has been deprecated, we may revisit this in future. Today we are using the release branch flow with no main branch._

### Example workflow for a feature branch

```bash
git checkout develop
git pull  # or equivalent to be sure you have the latest code
git checkout -b ERA-1111
```

Make your code changes.

```bash
git add <files that changed>
git commit -m "informative comment on code changes"
git push origin ERA-1111
```

Once you have completed work, use the Github interface to start a Pull Request on your branch to get it merged into the `develop` branch.

Delete your feature branch once it has been approved and merged into `develop` - we do that at the end of the PR process.

### Release Numbers

- **Major Change** 1.x to 2.x - The API contract is broken. Massive changes to the codebase.
- **Minor Change** 1.2 to 1.3 - New features, no major breaking changes.
- **Micro Change** 1.2.1 to 1.2.2 - Bug fixes, very small features.
