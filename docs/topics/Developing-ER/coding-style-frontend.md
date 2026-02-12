# Front-End Engineering

## JavaScript

The EarthRanger web application is written in React, and was originally bootstrapped using `create-react-app`.

The JavaScript coding style is enforced within the `das-web-react` development environment using ESLint, and inherits the [AirBnB JavaScript Style Guide](https://github.com/airbnb/javascript) as the basis for its rules and configuration. There are additional sets of React-specific guidelines applied as well. The full list of rules can be found in the project's `package.json` as developer dependencies prefixed either with `eslint-config` or `eslint-plugin`, and further rules are specified in the `.eslintrc` file. Any developer working within the front-end EarthRanger codebase should have ESLint running and should be self-correcting as they go along.

We favor composition over inheritance, legibility over terseness, and consistency across components. Functional components are preferred over class-based components, and whenever possible practice a "boy scouts" approach to the files you touch (i.e. leave them better than you found them).

Significant portions of the app are written using `redux` as a central store, but more recent code favors the [Context API](https://reactjs.org/docs/context.html) as a more extensible and portable means of managing state.

## CSS

The project's CSS is written using Sass.

- Use reusable code via variables, mixins, extensions, functions, etc whenever possible.
- When authoring class names, use functional names ("container", "sidebar", "feedList", etc) over descriptive names ("redBox", "leftSide", etc).
- Use `rem` units for sizing areas in relation to the page, and `em` units for self-contained areas of design in which a set of items need to scale in direct relationship to one another. _Do not use pixel values without an extremely good reason_.
- Media queries, the basis of our responsive resizing, should be captured as mixins to ensure consistency and re-use when possible.
- Make sure you're only writing new styles and values as necessary - always check `src/common/styles` first.

## HTML

Use semantic markup whenever possible. Use block and inline elements for block and inline components. Don't coerce elements to behave like other elements; use the natively correct ones instead. Buttons should invoke an action, links should invoke navigation. Etc. [When in doubt, look it up](https://learn-the-web.algonquindesign.ca/topics/html-semantics-cheat-sheet/). CSS Classes should describe the element's role (such as `className='header-menu'`), not its characteristics (such as `className='brown flex'`).

## Branching

Our branching strategy follows the basics of Gitflow. All new branches should be checked out from the `develop` branch. The name of the branch should match that of the ticket in Jira (ex: `git checkout -b DAS-7070`).

## Setting Up a Feature Branch Environment

If you're working on a significant or long-lived feature, you may want to host your work in our continuous integration pipeline so you may share the work with internal stakeholders for feedback and review.

To do this, you must:

- Create matching branches for `das` and `das-web-react` with a name matching the Jira ticket (for example: `DAS-1234`. The pipeline is a little delicate so keep it to ticket names; special characters won't deploy)
- Push both to remote
- Notify the DevOps team that you need a database initialized for your new branch

Once completed, your branch will be available at `https://<your-branch-name>.pamdas.org`, accessible with the default admin credentials. If you don't know the default admin credentials, contact your team leader or manager.
