Project EarthRanger aka DAS - Domain Awareness System
=================================================================

## Coding Agent Setup
As of Jan 27, 2026, the way is this:
We write our Agent context in [AGENTS.md](https://agents.md/), then link it for other cli's to find it

```
# Use Cursor's rules as the source of truth
ln -s .cursor/rules .claude/rules
```

Either link the files, or remember to @AGENTS.md in your claude prompt
```
ln -s AGENTS.md CLAUDE.md
ln -s AGENTS.md .cursorrules
```

## Onboarding

See the ER Onboarding documentation for help on setting up your developer workstation.
[OnBoarding](https://root.dev.pamdas.org/api/v1.0/docs/topics/Developing-ER/README.html)
