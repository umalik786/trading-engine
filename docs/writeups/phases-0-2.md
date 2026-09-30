# How I test that my backtester isn't lying to me

## 1. Why I built this

I've been trading CFDs for 3 years and understand what it takes to win at this game; for example, consistency when applying a specific profitable strategy alongside a risk management layer usually checks out in theory. The problem was always self-discipline — I would break my own rules, which would lead to deeper drawdown. The solution is to build a system that automates trading, but to automate trading you have to implement a strategy you can trust, and to trust a strategy's edge you must backtest it reliably. Available retail backtesting tools make it hard to check whether results are honest: look-ahead bias (using information that wouldn't have existed at the moment of the decision), understated costs, and test code that differs from live code. This engine solves both of the above problems: it is built so look-ahead bias can't get in, and the same code used for backtesting is used for live. It will tell you honestly if the strategy being tested has an edge. Secondly, the engine will trade automatically on the selected strategy. To build this engine, I write specifications and own the review and decision process, but Claude Code writes the implementation.

## 2. The real danger isn't crashes

Reliability can only be achieved if testing is thorough. Bugs do not always mean something crashed. If there is a persistent bug that produces a result which looks correct because the numbers agree with each other, but in fact they are wrong, then you'd end up using a strategy that would not perform live. Therefore it's important to test both cases, passes and purposeful fails, and be aware of any limitations.

## 3. Four times the system looked right and wasn't

**a. Every timestamp was off by 2–3 hours.**

Initially they looked correct because every bar was internally consistent. It turned out that MT5 returns times in the broker server's clock, which runs 2–3 hours ahead of UTC depending on the season. The spec itself said that MT5 returns UTC, but it doesn't. It was caught because a routine "no bar from the future" check fired. The first explanation offered was a glitch in the test environment: plausible, easy, and wrong. Proof of the fix was that gold's weekly close must align with 22:00 UTC in winter and 21:00 in summer. It does now after the fix. We cannot trust cheap explanations; everything should be validated by data.

**b. The broker invented twelve years of history.**

When I asked MT5 for a year that had no data at all, it didn't return nothing. It returned the nearest real bar, from outside the year I asked for. For the indices, whose data starts in December 2017, that meant the same December 2017 bar coming back for every empty year before it. Stored as-is, it would have planted a copy of that bar in every year back to 2005, misdated by up to twelve years. Every bar was valid, just in the wrong year. What gave it away: exactly one bar in every empty year, a pattern too regular to be real.

**c. A test that couldn't fail where I thought it could.**

On the look-ahead test, one constant did three jobs. When I tried to break the test on purpose, it still passed, because changing that one constant moved all three at once and they stayed consistent with each other. Claude Code and the chat review didn't spot it by reading. It is important to try to break a test deliberately so you can differentiate between plausible and true.

**d. A green result a cheating engine would also have passed.**

AlwaysLong matched my spreadsheet to the cent (5718.00). But on that week, bar 2's open happened to equal bar 1's close, so an engine filling at the wrong price would have scored exactly the same. I noticed that a bar's close and the next bar's open do not always match, so I tested at both price locations (bar open and previous bar close). I worked out both numbers (correct 4740.00 and cheating 4749.00). The engine matched the correct one, and the cheating one turned the test red, off by exactly 9.00. This showed that a test is only as good as the data's ability to show the bug. In this case, cheating means filling at a price the engine couldn't have known yet.

## 4. The one question

Without reading the code, I ask:

> "Show me this test failing when the thing it checks is broken."

It is important to do that so we can be assured that the engine would catch the bug, and don't just rely on passing.

## 5. What this does not prove

We are not currently proving whether a strategy makes money. That comes later, when a real strategy is tested against random entries. Also, prop-firm fills are simulated, so real trading costs cannot yet be validated. The look-ahead test only catches leaks that depend on the order of bars. A leak through something order-free, such as the maximum, minimum or sum of the whole dataset, would slip past it. A second test is planned.

## 6. What's next

Costs and position sizing come next in phase 3, then risk limits.
