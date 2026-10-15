"""analyse_losses.py - compare what the publisher sent with what the subscriber received (pilot run 1)."""
import re
from collections import Counter

# Only log lines from run 1 (publisher 11:32:12 to subscriber 11:32:29 CAT). Adjust for other runs.
START, END = "2026-10-12 11:32:00", "2026-10-12 11:33:00"

# Publisher line: "<date> <time> DEBUG sent mid=N topic=energy/meters/<id> event_time=<t>"
sent_re = re.compile(r"^(\S+ \S+) DEBUG sent mid=\d+ topic=energy/meters/(\d+) event_time=(\S+)")
# Subscriber line (run 1 wrote "stored", later versions write "received")
got_re = re.compile(r"^(\S+ \S+) DEBUG (?:stored|received) topic=energy/meters/(\d+) .*?event_time=(\S+)")

# 1. Messages in the order the publisher sent them, as (meter_id, event_time) pairs.
sent = []
with open("logs/pilot_publisher.log", encoding="utf-8") as f:
    for line in f:
        m = sent_re.match(line)
        if m and START <= m.group(1) <= END:
            sent.append((m.group(2), m.group(3)))

# 2. How many times the subscriber saw each pair (a Counter handles deliberate duplicates).
got = Counter()
with open("logs/pilot_subscriber.log", encoding="utf-8") as f:
    for line in f:
        m = got_re.match(line)
        if m and START <= m.group(1) <= END:
            got[(m.group(2), m.group(3))] += 1

# 3. Walk the sent list in order; a message is "missing" if no matching arrival is left.
missing = []                      # positions in send order (0 = first message sent)
for pos, key in enumerate(sent):
    if got[key] > 0:
        got[key] -= 1             # matched: use up one arrival
    else:
        missing.append(pos)

# 4. Group the missing positions into contiguous runs, to show the loss pattern.
runs = []
for pos in missing:
    if runs and pos == runs[-1][1] + 1:
        runs[-1][1] = pos         # extends the current run
    else:
        runs.append([pos, pos])   # starts a new run

print(f"Sent by publisher        : {len(sent)}")
print(f"Missing at subscriber    : {len(missing)}")
print(f"Number of missing runs   : {len(runs)}")
for a, b in runs[:15]:
    print(f"  send positions {a:>4} to {b:>4}  ({b - a + 1} messages)")
if len(runs) > 15:
    print(f"  ... and {len(runs) - 15} more runs")
print(f"Arrivals with no matching send: {sum(got.values())}")