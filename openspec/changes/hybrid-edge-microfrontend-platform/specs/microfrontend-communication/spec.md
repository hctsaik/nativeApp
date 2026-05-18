# Micro-Frontend Communication Specification

## ADDED Requirements

### Requirement: iframe-based enterprise app embedding

The portal SHALL embed enterprise React applications through iframe integration.

#### Scenario: Enterprise app is opened

- WHEN the user navigates to an enterprise application
- THEN the portal SHALL create an iframe using the configured application URL

### Requirement: Typed postMessage protocol

The portal and child application SHALL communicate using typed
`window.postMessage` envelopes.

#### Scenario: Child app becomes ready

- WHEN the child application is loaded
- THEN it SHALL send a `CHILD_READY` message to the portal

#### Scenario: Portal sends authentication token

- WHEN the portal receives a trusted `CHILD_READY` message
- THEN the portal MAY send an `AUTH_TOKEN` message to the child application

### Requirement: Message trust validation

Both host and child application SHALL validate message trust before acting.

#### Scenario: Message origin is not trusted

- WHEN a message is received from an unapproved origin
- THEN the receiver SHALL ignore the message

### Requirement: Route synchronization

The child application SHALL notify the portal when its internal route changes.

#### Scenario: Child route changes

- WHEN the child React Router location changes
- THEN the child application SHALL send a `ROUTE_CHANGED` message
- AND the portal SHALL update its own route or navigation state according to the
  configured synchronization policy

