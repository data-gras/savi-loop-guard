# Security Policy

## Scope

`savi-loop-guard` is a small, dependency-free, local-only detector. It
never makes a network call, never reads a credential, and never touches
anything outside the events you hand it in-process. That keeps the realistic
attack surface narrow (mainly: could a crafted `CallEvent` cause a crash,
excessive memory/CPU use, or an incorrect result an application might rely
on for safety), but "narrow" isn't "none"; please still report anything
that looks like a real vulnerability rather than assuming it's out of scope.

## Supported versions

Only the latest published version on PyPI is supported. Given this package
has no dependency tree of its own, a fix ships as the next patch release,
not a series of backports.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security concern.

Instead, email **contact@datagras.com** with a description of the issue and,
if possible, steps to reproduce it. You should get an acknowledgment within
a few business days. Once a fix is confirmed, we'll coordinate on
disclosure timing with you before anything is made public.

## What we consider in-scope

- A crafted or adversarial `CallEvent` sequence that crashes `record()`,
  `check()`, or `check_before_call()` instead of returning normally or
  raising the documented `LoopDetected`.
- A resource-exhaustion issue (unbounded memory/CPU growth) from realistic
  input sizes.
- Anything in the package that makes a network call or reads environment
  data it has no documented reason to; that would itself be a bug in the
  "zero network calls, ever" claim this package makes.
