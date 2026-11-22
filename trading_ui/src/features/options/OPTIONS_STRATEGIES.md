# Options Strategy Reference

This document is the implementation reference for the TAFM option strategy builder. All strategies are presented for analysis only; the application does not place orders.

## External Reference

- [Sensibull NIFTY Option Strategy Builder](https://web.sensibull.com/option-strategy-builder?instrument_symbol=NIFTY)
- Reference scope: strategy categories, preset names, and interaction flow.
- TAFM implementation uses original payoff/Greeks calculations and local Kite option-chain data; no external page code or article prose is copied.

## Notation

- `K1 < K2 < K3 < K4`: strike prices, ordered low to high.
- `C(K)` / `P(K)`: call / put at strike `K`.
- `LC`, `SC`, `LP`, `SP`: long call, short call, long put, short put.
- `F`: futures entry price; `S_T`: underlying price at expiry.
- Net debit is total premium paid. Net credit is total premium received.
- Profit/loss formulas below exclude brokerage, taxes, slippage, assignment, dividend adjustments, and exercise costs.
- For a one-point underlying move, option-leg P/L uses quantity or lot multiplier in the application.

## Bullish

### Buy Call
- **Outlook:** Moderately to strongly bullish; expects higher volatility or a move above strike before expiry.
- **Legs:** Buy 1 `C(K)`.
- **Net position:** Debit equal to call premium.
- **Max loss:** Premium paid.
- **Max profit:** Unlimited at expiry.
- **Breakeven:** `K + premium`.
- **Greeks:** Positive Delta, positive Gamma/Vega; negative Theta.
- **Best use:** Directional upside with limited loss. Avoid very low-delta deep OTM contracts unless accepting low probability.

### Sell Put
- **Outlook:** Bullish to neutral; underlying should remain above strike.
- **Legs:** Sell 1 `P(K)`.
- **Net position:** Credit equal to put premium.
- **Max loss:** `K - credit`, if underlying reaches zero.
- **Max profit:** Net credit.
- **Breakeven:** `K - premium`.
- **Greeks:** Positive Delta, negative Gamma/Vega; positive Theta.
- **Best use:** Bullish income with stock-like downside below strike. Requires sufficient margin and assignment capacity.

### Bull Call Spread
- **Outlook:** Moderately bullish to a known target.
- **Legs:** Buy 1 `C(K1)` and sell 1 `C(K2)`.
- **Net position:** Debit.
- **Max loss:** Net debit.
- **Max profit:** `K2 - K1 - debit`.
- **Breakeven:** `K1 + debit`.
- **Greeks:** Positive Delta; lower Gamma, Vega, and Theta exposure than a standalone long call.
- **Best use:** Defined-risk upside target with lower premium and reduced time-decay exposure.

### Bull Put Spread
- **Outlook:** Bullish to neutral; underlying should remain above the short put.
- **Legs:** Sell 1 `P(K2)` and buy 1 `P(K1)`.
- **Net position:** Credit.
- **Max loss:** `K2 - K1 - credit`.
- **Max profit:** Net credit.
- **Breakeven:** `K2 - credit`.
- **Greeks:** Positive Delta; negative Gamma/Vega; positive Theta.
- **Best use:** Defined-risk bullish credit alternative to a naked short put.

### Call Ratio Back Spread
- **Outlook:** Strong upside; relatively quiet downside or a quick move. Often volatility expansion friendly.
- **Legs:** Sell 1 `C(K1)` and buy 2 `C(K2)`; adjust ratio for intended neutrality at entry.
- **Net position:** Usually a small debit or credit.
- **Max loss:** Often occurs near `K2`: `K2 - K1 - net credit` (or plus net debit).
- **Max profit:** Unlimited above `K2`.
- **Breakeven:** Entry-dependent; use payoff graph for exact point(s).
- **Greeks:** Positive Vega/Gamma after the short-delta hedge; changes sharply with price and volatility.
- **Best use:** Explosive bullish move while limiting catastrophic downside if configured for small entry credit.

### Long Calendar with Calls
- **Outlook:** Neutral initially, then mildly bullish; benefits when short-dated option expires near strike and IV/risk relationships are favorable.
- **Legs:** Sell short-dated `C(K)` and buy longer-dated `C(K)`.
- **Net position:** Debit.
- **Max profit/loss:** Path-dependent; not fixed because the long leg retains time value.
- **Risk markers:** Short-leg pin risk, assignment, calendar IV skew, and event risk.
- **Greeks:** Usually positive Vega and Theta relative to the net position; Delta can be small.
- **Best use:** Horizontal volatility/time-structure view, especially with a near-term expiry target.

### Bull Condor
- **Outlook:** Moderately bullish but range-bound between two profitable bands.
- **Legs:** Bullish condor formed from four options; commonly buy `C(K1)`, sell `C(K2)`, sell `C(K3)`, buy `C(K4)` with selected asymmetric widths/skew.
- **Net position:** Debit or credit depending on strikes.
- **Max loss:** Debit (for debit form) or wing width less credit (for credit form).
- **Max profit:** Occurs between short strikes; exact amount is determined by net premium and widths.
- **Breakeven:** Two points; calculate from the active wing.
- **Greeks:** Positive or slightly positive Delta; short Gamma near the center; Theta depends on net premium.
- **Best use:** Directional move into a target range while defining both tails.

### Bull Butterfly
- **Outlook:** Bullish to a precise expiry target.
- **Legs:** Buy 1 `C(K1)`, sell 2 `C(K2)`, buy 1 `C(K3)` with intentionally skewed strikes or target body.
- **Net position:** Usually debit.
- **Max loss:** Net debit.
- **Max profit:** Occurs at the body strike; approximately `K2 - K1 - debit`, adjusted for wing widths.
- **Breakeven:** Use the rising and falling wings: entry-dependent.
- **Greeks:** Low Delta/Gamma near center; sharply changing local Greeks near strikes.
- **Best use:** Narrow bullish target with high reward-to-risk if the forecast is precise.

### Range Forward
- **Outlook:** Bullish directional view with a funded call component and downside obligation.
- **Legs:** Common form: buy a higher-strike `C(K2)` and sell a lower-strike `P(K1)`; variations tune strikes/premiums.
- **Net position:** Debit, credit, or zero-cost.
- **Max loss:** Substantial below the short put strike; potentially stock-like.
- **Max profit:** Unlimited above call strike.
- **Breakeven:** Depends on net premium; for long call leg use `K2 + debit`, with downside anchored by short put economics.
- **Greeks:** Positive Delta; short Gamma/Vega in the lower range and long Gamma/Vega in the upper range.
- **Best use:** Directional participation with premium offset; not a low-risk alternative to a vertical spread.

### Buy Future
- **Outlook:** Directionally bullish with full mark-to-market participation.
- **Legs:** Buy one futures contract.
- **Max loss/profit:** Both theoretically substantial in the relevant direction; daily variation margin applies.
- **Breakeven:** Futures entry, excluding costs/funding.
- **Greeks:** Delta-like exposure approximately one lot multiplier; not an option Gamma/Vega position.
- **Best use:** Direct directional exposure, not within an options-only spread unless combined intentionally.

### Long Synthetic Future
- **Outlook:** Bullish, similar delta to a long future.
- **Legs:** Buy `C(K)` and sell `P(K)` at the same strike and expiry.
- **Net position:** Usually close to small debit/credit near ATM.
- **Max profit/loss:** Similar to long futures within expiry payoff parity, less financing effects.
- **Breakeven:** Approximately `K + call premium - put premium`.
- **Greeks:** Positive Delta near one; Gamma and Vega mostly offset but imperfectly due to skew and live prices.
- **Best use:** Futures-like directional exposure, often with strike flexibility.

## Bearish

### Buy Put
- **Outlook:** Moderately to strongly bearish.
- **Legs:** Buy 1 `P(K)`.
- **Max loss:** Premium paid.
- **Max profit:** `K - premium` if underlying falls to zero.
- **Breakeven:** `K - premium`.
- **Greeks:** Negative Delta; positive Gamma/Vega; negative Theta.
- **Best use:** Defined-risk downside or hedge against a portfolio drawdown.

### Sell Call
- **Outlook:** Bearish to neutral; underlying should remain below strike.
- **Legs:** Sell 1 `C(K)`.
- **Max profit:** Premium received.
- **Max loss:** Unlimited.
- **Breakeven:** `K + premium`.
- **Greeks:** Negative Delta/Gamma/Vega; positive Theta.
- **Best use:** Bearish or income thesis only with margin and exercise-risk controls.

### Bear Call Spread
- **Outlook:** Moderately bearish to neutral.
- **Legs:** Sell `C(K1)`, buy `C(K2)`.
- **Net position:** Credit.
- **Max profit:** Net credit.
- **Max loss:** `K2 - K1 - credit`.
- **Breakeven:** `K1 + credit`.
- **Greeks:** Negative Delta, negative Gamma/Vega, positive Theta.

### Bear Put Spread
- **Outlook:** Moderately bearish to a target.
- **Legs:** Buy `P(K2)`, sell `P(K1)`.
- **Net position:** Debit.
- **Max loss:** Debit.
- **Max profit:** `K2 - K1 - debit`.
- **Breakeven:** `K2 - debit`.
- **Greeks:** Negative Delta; reduced Gamma/Vega/Theta magnitude versus a standalone put.

### Put Ratio Back Spread
- **Outlook:** Strong downside; may accept little or no directional loss below only after a move.
- **Legs:** Sell 1 `P(K2)`, buy 2 `P(K1)`; tune for small credit/debit.
- **Max loss:** Occurs near lower body strike; entry-dependent.
- **Max profit:** Substantial below the lower strike, limited by zero floor.
- **Breakevens:** Two or one, depending on entry credit; derive from payoff graph.
- **Greeks:** Positive Vega/Gamma, negative Delta on a downside acceleration.

### Long Calendar with Puts
- **Outlook:** Neutral to bearish toward the first expiry, then neutral with remaining long put value.
- **Legs:** Sell short-dated `P(K)`, buy longer-dated `P(K)`.
- **Risk:** Assignment, pin risk, term-structure changes, and event IV reversal.
- **Greeks:** Usually long Vega and relative long Theta depending on the entry skew.
- **Best use:** Expected stabilization near strike after a bearish event or downside skew setup.

### Bear Condor
- **Outlook:** Bearish but expects expiry in a selected lower range.
- **Legs:** Four-leg condor with strikes/sloping premiums biased below current spot.
- **Payoff:** Defined loss outside wings and maximum gain within inner band.
- **Greeks:** Net negative Delta; typically short Gamma and positive Theta near center.
- **Best use:** Controlled bearish range target.

### Bear Butterfly
- **Outlook:** Bearish with a precise lower target.
- **Legs:** Buy outer put wings and sell two puts at the target/body strike, often lower than spot.
- **Max loss:** Net debit/credit-dependent outer risk.
- **Max profit:** At body strike.
- **Best use:** Narrow bearish forecast with limited risk.

### Risk Reversal
- **Outlook:** Bearish in one form: buy OTM put and sell OTM call (bullish reversal uses opposite legs).
- **Legs:** Long `P(K1)` plus short `C(K2)` for bearish exposure.
- **Max loss/profit:** Short call tail can be unlimited; put limits only downside risk.
- **Greeks:** Negative Delta; skew determines Vega/Gamma balance.
- **Best use:** Directional exposure with IV-skew financing, accepting short-option tail risk.

### Sell Future
- **Outlook:** Bearish.
- **Legs:** Sell one future.
- **Payoff:** Linear; profits as market falls and losses as market rises.
- **Risk:** Variation margin, gap risk, leverage.
- **Best use:** Direct bearish exposure rather than a finite-risk option structure.

### Short Synthetic Future
- **Outlook:** Bearish, similar delta to short future.
- **Legs:** Sell `C(K)`, buy `P(K)` at same strike/expiry.
- **Breakeven:** Approximately `K + call premium - put premium`.
- **Greeks:** Negative Delta near one with much of Gamma/Vega offset.
- **Best use:** Futures-like downside exposure with selectable synthetic strike.

## Neutral

### Short Straddle
- **Outlook:** Neutral with falling/range-bound realized volatility.
- **Legs:** Sell ATM `C(K)` and ATM `P(K)`.
- **Max profit:** Total credit.
- **Max loss:** Unlimited in either tail.
- **Breakevens:** `K ± credit`.
- **Greeks:** Short Gamma/Vega, positive Theta, Delta near zero at entry.
- **Risk:** Gap, event, IV spike, and assignment/early exercise.

### Iron Butterfly
- **Outlook:** Neutral, sharply pinned to a target strike.
- **Legs:** Sell ATM call and put; buy OTM call and put wings.
- **Max loss:** Wing width minus credit.
- **Max profit:** Net credit at target.
- **Breakevens:** Approximately `K ± credit`.
- **Best use:** Defined-risk short-volatility alternative to a naked straddle.

### Short Strangle
- **Outlook:** Broadly neutral; market expected to remain inside two outer breakevens.
- **Legs:** Sell OTM `P(K1)` and OTM `C(K2)`.
- **Max loss:** Unlimited in both tails.
- **Max profit:** Net credit.
- **Breakevens:** `K1 - credit`, `K2 + credit` (adjust per leg premiums for precise totals).
- **Greeks:** Short Vega/Gamma, positive Theta.

### Short Iron Condor
- **Outlook:** Stable underlying inside a range.
- **Legs:** Buy `P(K1)`, sell `P(K2)`, sell `C(K3)`, buy `C(K4)`.
- **Max loss:** Put wing width or call wing width minus credit.
- **Max profit:** Net credit.
- **Breakevens:** Short put strike minus credit; short call strike plus credit.
- **Greeks:** Short Gamma/Vega, positive Theta, near-zero Delta if centered.

### Batman
- **Outlook:** Primarily range-bound with a stepped payoff shape.
- **Legs:** Usually constructed from put/call wings and multiple short/long bodies to create a broad central plateau. Confirm exact strikes in builder.
- **Risk:** Defined once all wings are included; leg asymmetry can bias Delta.
- **Greeks:** Short Gamma/positive Theta in profitable plateau, with changing Greeks near edges.

### Double Plateau
- **Outlook:** Neutral with two target premium ranges rather than one central strike.
- **Legs:** Multi-leg butterfly/condor combinations producing two flat profit regions.
- **Risk:** Defined by outer wings; premium curve is highly strike-selection dependent.
- **Best use:** Two likely settlement zones with protected tails.

### Jade Lizard
- **Outlook:** Neutral-to-bullish.
- **Legs:** Sell OTM put, sell OTM call spread (short call plus farther long call); choose call side credit at least equal to put-side spread risk for upside-no-risk intent.
- **Max loss:** Defined on upside; downside retains substantial short-put risk.
- **Greeks:** Net short Vega/Gamma, positive Theta, usually positive Delta.

### Reverse Jade Lizard
- **Outlook:** Neutral-to-bearish.
- **Legs:** Sell OTM call plus sell an OTM put spread (short nearer put, long farther put).
- **Max loss:** Downside defined by put spread width; upside retains uncapped short-call risk unless separately hedged.
- **Greeks:** Short Vega/Gamma, positive Theta, usually negative Delta.

## Others

### Call Ratio Spread
- **Outlook:** Mildly bullish or neutral but not beyond the dangerous upside zone.
- **Legs:** Buy 1 `C(K1)`, sell 2 `C(K2)`; variations adjust financing.
- **Risk:** Loss above upper breakeven can become unlimited because of extra short call.
- **Greeks:** Short Gamma/Vega at high prices; positive Delta initially then may turn negative.

### Put Ratio Spread
- **Outlook:** Mildly bearish or neutral, but not a crash beyond the lower zone.
- **Legs:** Buy 1 `P(K2)`, sell 2 `P(K1)`.
- **Risk:** Substantial loss below lower breakeven, bounded by underlying zero.
- **Greeks:** Short Gamma/Vega at low prices; negative Delta initially then may turn positive.

### Long Straddle
- **Outlook:** Large move, direction uncertain; IV expansion helpful.
- **Legs:** Buy ATM `C(K)` and `P(K)`.
- **Max loss:** Total debit.
- **Max profit:** Unlimited above, substantial below.
- **Breakevens:** `K ± total premium`.
- **Greeks:** Long Gamma/Vega, negative Theta, Delta near zero at entry.

### Long Iron Butterfly
- **Outlook:** Large move away from center, direction uncertain, but with capped risk and capped reward.
- **Legs:** Buy ATM call and put; sell farther call and put wings.
- **Max loss:** Net debit.
- **Max profit:** Wing width minus debit in either tail, depending on exact construction.
- **Greeks:** Long Gamma/Vega near expiry tails; negative Theta near movement target.

### Long Strangle
- **Outlook:** Large move, direction uncertain; wider breakeven range than straddle.
- **Legs:** Buy OTM `C(K2)` and OTM `P(K1)`.
- **Max loss:** Debit.
- **Breakevens:** `K1 - debit`, `K2 + debit` (precise total uses whole position debit).
- **Greeks:** Long Gamma/Vega, negative Theta.

### Long Iron Condor
- **Outlook:** Breakout from a range, direction uncertain, with defined risk/reward.
- **Legs:** Buy inner put/call and sell outer wings: buy `P(K2)`, sell `P(K1)`, buy `C(K3)`, sell `C(K4)`.
- **Max loss:** Net debit.
- **Max profit:** Wing width minus debit in the tails.
- **Best use:** Defined-risk range breakout when straddle/strangle premium is high.

### Strap
- **Outlook:** Large move with bullish directional bias.
- **Legs:** Buy 2 ATM calls and 1 ATM put.
- **Max loss:** Total debit.
- **Max profit:** Unlimited above; substantial below.
- **Greeks:** Positive Delta, long Gamma/Vega, negative Theta.

### Strip
- **Outlook:** Large move with bearish directional bias.
- **Legs:** Buy 1 ATM call and 2 ATM puts.
- **Max loss:** Total debit.
- **Max profit:** Large below, unlimited above.
- **Greeks:** Negative Delta, long Gamma/Vega, negative Theta.

## Builder Rules

1. The ATM strike is recomputed from the nearest live underlying price.
2. Every leg stores side, option type, strike, lots, and editable premium.
3. Expiry P/L per leg is `sideSign * quantity * (intrinsicValue - premium)` for long legs, and its exact inverse for short legs.
4. Net premium is positive for credit and negative for debit.
5. Position Greeks are the lot-adjusted sum of leg Greeks with short legs negated.
6. Strategies with multiple expiries require separate expiry-aware legs; a single-expiry payoff chart must not be used for their time-series P/L.
7. Naked short options and ratio structures must visibly preserve tail risk.
8. All calculations are analytical estimates until charges, slippage, bid/ask, and assignment are included.
