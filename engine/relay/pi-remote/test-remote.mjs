// familiar-remote's pure parts (R3b): who is away, what the phone shows, what an answer means.
// Run: node engine/relay/pi-remote/test-remote.mjs   (node >= 23 strips the types)
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { awayAfterSeconds, awayReason, permissionTitle, verdict, PERMISSION_OPTIONS,
         CAPPED_YES, capped, permissionOptions }
  from "./index.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
let n = 0;
const t = (name, fn) => { fn(); n++; console.log(`ok    ${name}`); };

t("away_after is read from the real relay.yaml", () => {
  const cfg = fs.readFileSync(path.resolve(here, "../../../config/relay/relay.yaml"), "utf8");
  assert.equal(awayAfterSeconds(cfg), 600);
  assert.equal(awayAfterSeconds("defaults:\n  away_after: 90\n"), 90);
  assert.equal(awayAfterSeconds("defaults: {}\n"), 600);
});

const base = { now: 1_000_000, lastInput: 1_000_000, awayAfterS: 600, locked: false, awaySince: null };
t("present by default, away after the idle window", () => {
  assert.equal(awayReason(base), null);
  assert.equal(awayReason({ ...base, now: base.now + 599_000 }), null);
  assert.match(awayReason({ ...base, now: base.now + 600_000 }), /no input for 600s/);
});
t("a locked screen is away at once", () => {
  assert.equal(awayReason({ ...base, locked: true }), "the screen is locked");
});
t("/away counts until local input after it", () => {
  assert.equal(awayReason({ ...base, awaySince: (base.lastInput + 1000) / 1000 }), "/away from the phone");
  assert.equal(awayReason({ ...base, awaySince: (base.lastInput - 1000) / 1000 }), null);
});

t("a permission ask shows tool, rule and command", () => {
  const title = permissionTitle({ toolName: "bash", command: "rtk git push origin main",
    payload: { request: { surface: "bash", matchedPattern: "rtk git push *" } } });
  assert.equal(title, "Permission Required\ntool    : bash\nrule    : rtk git push *\ncommand : rtk git push origin main");
  const p = permissionTitle({ toolName: "read", path: "/etc/hosts",
    payload: { request: { surface: "external_directory", matchedPattern: "*" } } });
  assert.match(p, /surface : external_directory/);
  assert.match(p, /path    : \/etc\/hosts/);
});

t("answers become verdicts; a worded reply is a denial the model reads", () => {
  assert.deepEqual(PERMISSION_OPTIONS, ["Yes", "No", "No, provide reason"]);
  assert.deepEqual(verdict({ value: "Yes" }), { kind: "allow" });
  assert.equal(verdict({ value: "No" }).kind, "deny");
  assert.deepEqual(verdict({ value: null, text: "push to the fork" }),
    { kind: "deny", reason: "The user answered from the phone: push to the fork" });
  assert.deepEqual(verdict({ cancelled: true, withdrawn: "back" }), { kind: "defer" });
  assert.deepEqual(verdict(null), { kind: "defer" });
});


t("a capped path ask says so on the phone, and its Yes hands the decision to the terminal", () => {
  const path = { toolName: "write", surface: "path_write", path: "/srv/vault/config/practice/user/a.md" };
  assert.ok(capped(path) && capped({ surface: "external_directory_write" }));
  assert.ok(!capped({ toolName: "bash", command: "git push" }));
  assert.deepEqual(permissionOptions(path), [CAPPED_YES, "No", "No, provide reason"]);
  assert.deepEqual(permissionOptions({ toolName: "bash" }), PERMISSION_OPTIONS);
  assert.match(permissionTitle(path), /confirmed at the terminal/);
  assert.deepEqual(verdict({ value: CAPPED_YES }), { kind: "defer" });
  assert.equal(verdict({ value: "No" }).kind, "deny", "a phone denial still decides");
});


console.log(`\n${n} passed`);
