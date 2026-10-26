"""secrets -- the shapes that are a secret or a leak in ANY tree, one list for two gates.

WHY HERE. `checks/publish_scan.py` finds them in a tree before publishing, and
`relay/redact.py` masks them before anything leaves this machine for Telegram.
Both must agree on what one looks like, and `lib` is the one package both may
import (the import order: lib <- knowledge <- harness <- context <- consolidation
<- cli). Importing the scanner from the relay instead made `checks` mean two
modules in one process -- `engine/checks/checks.py` and the `checks/` directory
-- which broke the registry's own tests whenever the relay was collected first
(2026-10-20).

Each shape is `(name, regex, keep)`: `name` is what a declaration names, and
`keep(match_text)` filters the shape's false positives -- the reserved names
below, never a file of this tree.
"""
from __future__ import annotations

import re

# Names that are a PLACEHOLDER for an account rather than an account. A test
# fixture says `/home/someone`; a real machine says its user's name. The shape
# check cannot tell them apart, so the generic ones are named here and everything
# else stays a hit -- a fixture naming a real stranger is a hit too, and that
# is the correct reading of "an absolute home path in a published tree".
PLACEHOLDER_HOMES = {
    "user", "u", "you", "yourname", "me", "someone", "someuser", "username",
    "example", "test", "tester", "runner", "home", "name", "alice", "bob",
}

# Addresses that cannot disclose anything: the RFC 2606/6761 reserved names,
# and RFC 1918's documentation range is NOT included -- a private network
# address in a published file is a fact about the network it sits on.
RESERVED_MAIL = (
    "example.com", "example.net", "example.org", "localhost",
)
RESERVED_SUFFIX = (".invalid", ".test", ".example", ".local", ".localhost")

# Addresses that are not a host: loopback and the wildcard bind.
NOT_A_HOST = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}

# The shapes that are wrong in ANY tree. Each is `(name, pattern, keep)`; the
# name is what a declaration names, so it is stable and short, and `keep`
# filters the shape's false positives -- the reserved names above.
BUILTIN = (
    # An email address, but not a VCS remote: `git@github.com:owner/repo` is a
    # URL, and every skill's frontmatter carries one. The TLD must be
    # alphabetic, so a `package@1.18.18` version string is not an address.
    ("email", r"(?<![\w.+@-])(?!git@)[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+"
              r"[A-Za-z]{2,}",
     lambda s: not (s.split("@", 1)[1].lower() in RESERVED_MAIL
                    or s.split("@", 1)[1].lower().endswith(RESERVED_SUFFIX))),
    ("ipv4", r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
             r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?![\w.])",
     lambda s: s not in NOT_A_HOST and not s.startswith("127.")),
    ("home-path", r"/(?:home|Users)/[A-Za-z][\w.-]*",
     lambda s: s.rsplit("/", 1)[1].lower() not in PLACEHOLDER_HOMES),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", None),
    ("token", r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"
             r"|(?<![\w-])sk-[A-Za-z0-9-]{20,}"
             r"|AKIA[0-9A-Z]{16}"
             r"|xox[baprs]-[A-Za-z0-9-]{10,}", None),
    ("restic-passphrase", r"(?:RESTIC_PASSWORD|RESTIC_PASS|restic[-_ ]pass"
                          r"(?:phrase|word))\s*[:=]\s*\S+", None),
)


#: The shapes as compiled patterns, which is what both gates reuse.
SHAPES = {name: re.compile(rx) for name, rx, _keep in BUILTIN}
