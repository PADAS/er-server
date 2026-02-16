# Development Practices

The engineering team develops EarthRanger using an agile development process. We work in two week increments called a sprint. Work is defined as a series of stories which we document in a backlog. The stories in the backlog are organized in priority order. In this way, we select the top stories in the backlog at the start of a sprint. We explore the stories and commit to a set of them to be completed by the end of the two week cycle. The result of the sprint is ready for release to our customers.

## Feature/Story Development

Stories describe a feature. This feature could be requested by our customers, our Product Owner, and our own team. A story describes an outcome and is negotiated between the Product Owner and development team. The Product Owner is the conduit back to the customer in most cases.

### Customer Stories

- New Features
- Change in existing functionality

### Engineering Team Stories

- Technical debt - performance optimization for scale, security updates, library deprecation
- UI fit and finish

## Backlog Scrub

Before the story is selected into a sprint, we perform a final review of the story during a backlog scrub prior to sprint planning. The backlog scrub is to review and ensure a story has enough description and/or acceptance criteria for the development team to build and release the feature.

Attendees to the backlog scrub include development heads, QA, product owner and engineering manager. Additionally, can invite others, as necessary.

The next gate for a story is Sprint Planning.

## Backlog Item Estimation

Story estimation or backlog item estimation provides a way for the team to estimate the time and effort to complete a backlog item. This process is team dependent as it relies on a team setting a baseline and making future estimates from this collective understanding.

The Fibonacci sequence provides an increasing estimation number that aligns well with how a person can reason about the size of a story based on some doubling of the effort. For instance, I know how much effort Story One took and rate this a 1, and I estimate the new story will take twice as long. A doubling.

Our [Fibonacci Sequence](https://www.mountaingoatsoftware.com/blog/why-the-fibonacci-sequence-works-well-for-estimating) takes cues from Mike Cohn, rounding a few numbers down.

**1, 2, 3, 5, 8, 13, 20, 40 and 100**

How do we estimate with the whole team considering everyone's skill and knowledge?

- Estimation is not voting. It's expected the team to discuss the estimate and item under consideration.
- The person with the skills needed for a story naturally have more credibility for the estimate.
- Estimates are not absolute; they are relative to previously known items.
- Everyone has a role to ask questions and compare to previous stories and situations.

## Sprint Cycle

As described earlier, the sprint cycle is a two-week work cycle. We have a big meeting at the beginning (Sprint Planning) to commit to the work to be done.

### Sprint Planning

Prior to sprint planning, a Backlog Scrub has refined the stories that are ready for selection into the sprint.

### Development during a Sprint

#### Choosing a Story

During sprint planning, we will have selected a specific set of stories that we all agreed can be accomplished during the sprint. If we have closed out all stories, please contact the PM/Development Manager or the development lead about selecting a non-sprint story to work on.

#### Story Development

##### Artifacts of story development

Update the Jira ticket to include the following artifacts as the story develops:

- Test cases, test data
- Notes on development useful to QA, PO, deployment, and support
- Deployment documentation - work with Support
- Document any new server and Vault settings
- For API stories, interactive documentation on API usage and parameters. Requirement that a new or updated API be visible in the [ER Server API Browser](https://develop.pamdas.org/api/v1.0/docs/interactive/)
- Device Integrations - for device integrations:
  - Procedure for an installer to backfill historic data
  - Monitoring - how do we monitor the integration for errors
  - Polling intervals - configuration for polling, what's possible and recommended by API vendor
  - Upon completion of implementing in production environment:
    - Disconnect the data feed from develop environment
    - Delete any historic data from develop environment
      - Look up the GUID of the source provider used then execute the following Django management command on that pipeline:
        ```bash
        echo "<source provider guid>" | uv run python3 manage.py purge_observation source_provider
        ```
- Jira Ticket number included in PR

##### Pre-work before writing code

- Review acceptance criteria. Does it describe the desired outcome?
- Discuss with QA testing approaches, develop testing plan
- What are some applicable tests (do I have data sets to test against)?
- UI mockups - if this is a user facing story? Work with UI developer.

##### User Messaging

Consider an ER user when writing user facing features. How do they expect to use the feature, what are the ergonomics and what are the possible errors?

Write the error messages to be decipherable by ordinary users, not just a software developer. Refrain from simply re-using errors coming from other systems. Translate these into ER friendly error messages. Provide a "more" option for a tech savvy user to see detailed information on the error. This to be used when calling ER tech support.

User facing messages should be marked for localization using Django's localization tools `_("")`.

See also: [User-facing Messages](user-facing-messages.md)

##### Pull Requests (PR)

Follow the steps below when you are ready to get feedback on your development work.

- All unit tests should pass, be sure to run them.
- Create the PR in GitHub, fill out the description and include a link to the Jira Ticket.
- Update the status of the associated Jira Ticket to Pull Request as well as adding a link to the GitHub PR.
- Pull requests are to be reviewed by at least 2 developers not working on the same story. We like to see review by others to provide feedback and general knowledge sharing.
- Depending on the story type (back-end or front-end), the Back-end Lead or Front-end Lead respectively should be asked to review.
- Each reviewer should run the code locally on their machine and exercise the code as much as possible.

### Work Priorities

To ensure we keep PRs moving along which allows us to close out stories, the following describes how to prioritize your work.

1. **High Priority Bugs** - if one has been assigned to you, this is your priority until finished.
   1. Hotfix work
   2. P0, P1
2. **Review and address feedback** on your story that is in PR. When setting up a PR, request reviewers using the GitHub tool as well as sending a Slack message or some other means so that you know they have acknowledged the request.
3. **Peer review** any stories you have been requested to review. Spend time on this to be sure you provide the best feedback possible. Once you see your feedback on the PR has been addressed either acknowledge or ask for further clarification.
4. **Continue working** on your regularly scheduled work/story.

### Bugs and Issues

If at any time during your daily work you come across what you consider a bug or issue do the following:

1. Document expected and actual results at a minimum. Create the bug in the backlog.
2. Talk with QA and development manager or lead. We can then decide on next steps.
3. Anything below a P0 bug/issue is triaged during scrum for next steps.
4. Follow branching standards for Hotfixes: [Source Code Branching - Hot Fix Branches](source-code-branching.md#hot-fix-branches)

### GitHub integration with Jira

We can automate changing Jira story states, for example moving from Progress to "In Pull Request". We do this using the [Jira Smart Commit feature](https://support.atlassian.com/jira-software-cloud/docs/process-issues-with-smart-commits/). Further, it matches the GitHub and Jira user by the email address between the two accounts.

The two commands we will use are comments and transition. Comment allows you to push a git commit comment into an existing Jira Story/Task/Subtask/Bug by specifying the Jira ID. The other is the Transition command that provides a mechanism to use a Git commit message to transition a Jira Story.

#### Comment

```
<ignored text> <ISSUE_KEY> <ignored text> #comment <comment_string>
```

Example: `DAS-6159 #comment Added the "Auto-end" description to patrol history`

#### Transition

```
<ignored text> <ISSUE_KEY> <ignored text> #<transition_name> #comment <comment_string>
```

Example: `DAS-6159 #progress #comment started work on this story`

## Mid-Sprint Demos

## Sprint Review

## Retrospective

This ceremony allows the team to look back on the work that was just completed and identify items that could be improved.

All the team goes through the team's inputs in every column. At the end of the session, some action items are defined based on the team's inputs.
