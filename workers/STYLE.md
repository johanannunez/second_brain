# Style rules for everything workers write to Jo

- Never use em dashes or en dashes anywhere, including code blocks. Use commas, colons, periods, or " · ".
- Status marks go at the start of a line, never the end: "✅ Checkouts: none today". Legend: ✅ all clear · ⚠️ watch · 🔴 must do today (3 at most per run) · 🆕 created this run · 💡 revenue idea · 🕐 timing change · 🔜 upcoming.
- Properties: street and unit only, in bold, such as **524 S Sycamore Ave, Unit B**. No city, state or zip.
- No paragraph blobs. Bullets or cards, one item per bullet. If a bullet chains three thoughts with commas, split it into sub-bullets.
- Blank line before every heading and between cards; "---" between property cards.
- Suggested replies go in fenced code blocks, English first, plus a Spanish block when the person writes in Spanish.
- Each fact appears in exactly one section. "Today's actions" holds pointers only. Anything already handled gets one ✅ line.
- "Nothing to report." only when a source answered with zero results. When a source failed, keep the section and write "⚠️ {Source} unavailable ({short error}), may be incomplete", and lead the Slack DM with the failure. Never skip a source silently.
- Never state a fact, name, amount, time or status that isn't in this run's data.json. If you can't verify something, write "unverified" and what's missing. Wrong but confident is the worst failure.
- Guests appear by first name only. Never write a code, password, contact detail or account number.
- Slack DM (the notify action): first sentence 80 characters or fewer and complete on its own (the most urgent item and its deadline), then 2 to 4 short fragments separated by " | ", about 200 characters total, plain text, ending with the link to the file. With nothing urgent, lead with "All clear:" and the day's counts. Don't invent urgency.
