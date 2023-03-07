# User-facing Messages

## Error Messaging

### Key principles when formatting a message to the user

- What happened
- Why
- How can user correct the input
- If not, who should they contact
- Don't:
  - Use technical jargon
  - Be confusing, instead be clear and concrete
  - Use negative words

## Django Admin

Here we talk about the possible ways to give feedback to the user.

1. Generalize the error displayed to the user.
2. If we know common errors and have instructions to try again or do differently, display those. Spoken in our words (not the 3rd party library or API).
3. Provide a collapsed Details section where we show the exact details of the error response (for instance if it's GFW, display their message. If it's a 3rd party library we are using, display the exception message from that library).

### Handling Common Errors

There are a class of common validation errors when saving models in admins.

Inline errors are standard Django Admin validation messages.
