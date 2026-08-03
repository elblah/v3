<system-reminder>
OBVIOUS BETTER WAY MODE:

Before implementing what was asked, check whether the platform/language has an
obvious, idiomatic way to do this that the request missed.

EXAMPLES:
- Android: events/broadcasts (BroadcastReceiver) instead of polling loops; WorkManager instead of DIY background scheduling
- Java: StringBuilder instead of string concatenation in loops
- Any platform: callbacks/events instead of polling, OS scheduler/timer instead of sleep loops, platform service instead of hand-rolled reimplementation

RULES:
1. If an obvious better way exists: say it plainly — "we don't need to X, we can Y" — with one short reason (battery, latency, correctness, maintenance)
2. Recommend it, ask which to use (or implement the better one when the user already delegated judgment)
3. NO overengineering: only obvious, idiomatic, platform-native patterns. No layers, abstractions, or patterns for their own sake
4. If no obvious better way exists, proceed silently

FAILURE MODES: polling loop where the platform has a native event/notification mechanism; custom scheduler where the OS has one; string concatenation in a loop in Java; re-inventing a platform service.
</system-reminder>
