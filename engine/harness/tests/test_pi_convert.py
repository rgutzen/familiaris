"""10b's `read` hook (`pi-convert`): a successful `read` of a document is
replaced by its markdown, cached under its content hash and cited by that
file's line numbers; anything else passes through untouched."""
import json
import pathlib
import shutil
import subprocess

import pytest

EXT = pathlib.Path(__file__).resolve().parents[1] / "pi-convert/index.ts"

def node():
    exe = shutil.which("node")
    if exe is None:
        pytest.skip("node is not installed")
    return exe


def js(script, *args):
    p = subprocess.run([node(), "--input-type=module", "-e", script, str(EXT), *map(str, args)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


CONVERT = r"""
const fs = await import("node:fs");
const path = await import("node:path");
const [ext, cacheDir, doc, body] = process.argv.slice(1);
const m = await import(ext);
const calls = [];
const run = async (cmd, args) => {
  calls.push([cmd, ...args]);
  if (body === "FAIL") throw new Error("boom");
  const out = cmd === "docling" ? path.join(args.at(-1), path.parse(args[0]).name + ".md") : args[2];
  fs.writeFileSync(out, body);
};
const r = [];
for (let i = 0; i < 2; i++) r.push(await m.convert(doc, run, cacheDir).catch((e) => "ERR " + e.message));
console.log(JSON.stringify({ r, calls, left: fs.readdirSync(cacheDir) }));
"""


@pytest.mark.parametrize("suffix,backend", [(".pdf", "docling"), (".docx", "markitdown"), (".XLSX", "markitdown")])
def test_convert_runs_the_backend_once_and_caches_by_content(tmp_path, suffix, backend):
    doc = tmp_path / f"paper{suffix}"
    doc.write_bytes(b"%PDF fake bytes")
    got = js(CONVERT, tmp_path / "cache", doc, "# Title\nbody\n")
    first, second = got["r"]
    assert first == second and first.endswith(".md"), "the second read hits the cache"
    assert [c[0] for c in got["calls"]] == [backend], "one conversion, by the extension's backend"
    assert pathlib.Path(first).read_text() == "# Title\nbody\n"
    assert got["left"] == [pathlib.Path(first).name], "no work directory is left behind"


@pytest.mark.parametrize("body,err", [("FAIL", "boom"), ("  \n", "found no text")])
def test_convert_failure_caches_nothing(tmp_path, body, err):
    doc = tmp_path / "scan.pdf"
    doc.write_bytes(b"x")
    got = js(CONVERT, tmp_path / "cache", doc, body)
    assert all(r.startswith("ERR") and err in r for r in got["r"])
    assert len(got["calls"]) == 2, "a failure is retried on the next read, not cached"
    assert got["left"] == []


WINDOW = r"""
const m = await import(process.argv[1]);
const text = Array.from({ length: 2500 }, (_, i) => `line ${i + 1}`).join("\n") + "\n";
const big = Array.from({ length: 100 }, () => "x".repeat(1000)).join("\n");
console.log(JSON.stringify({
  head: m.window(text).split("\n").slice(0, 2),
  tail: m.window(text).split("\n").slice(-1)[0],
  mid: m.window(text, 2400, 3).split("\n"),
  end: m.window(text, 2499).split("\n"),
  bytes: m.window(big).split("\n").slice(-1)[0],
  resolved: [m.resolvePath("@a/b.pdf", "/w"), m.resolvePath("/abs.docx", "/w")],
}));
"""


def test_window_pages_like_read():
    got = js(WINDOW)
    assert got["head"] == ["line 1", "line 2"]
    assert got["tail"] == "[500 more lines in file. Use offset=2001 to continue.]"
    assert got["mid"] == ["line 2400", "line 2401", "line 2402", "",
                          "[98 more lines in file. Use offset=2403 to continue.]"]
    assert got["end"] == ["line 2499", "line 2500"]
    assert got["bytes"] == "[49 more lines in file. Use offset=52 to continue.]", "50 KB cap: 51 lines of 1,001 bytes fit"
    assert got["resolved"] == ["/w/a/b.pdf", "/abs.docx"]


HANDLER = r"""
const [ext, cacheDir, doc] = process.argv.slice(1);
process.env.XDG_CACHE_HOME = cacheDir;
const m = await import(ext);
let h;
m.default({ on: (name, f) => { if (name === "tool_result") h = f; } });
const ctx = { cwd: "/" };
const raw = [{ type: "text", text: "PK\u0003\u0004 garbage" }];
const out = {
  other_tool: await h({ toolName: "bash", input: { path: doc }, content: raw }, ctx) ?? null,
  blocked: await h({ toolName: "read", isError: true, input: { path: doc }, content: raw }, ctx) ?? null,
  text_file: await h({ toolName: "read", input: { path: "/etc/hostname" }, content: raw }, ctx) ?? null,
  doc: await h({ toolName: "read", input: { path: doc, offset: 3, limit: 2 }, content: raw }, ctx),
};
console.log(JSON.stringify(out));
"""


def test_handler_replaces_only_a_successful_document_read(tmp_path):
    """Needs markitdown on PATH: the handler runs the real backend."""
    if shutil.which("markitdown") is None or shutil.which("pandoc") is None:
        pytest.skip("markitdown or pandoc is not installed")
    src = tmp_path / "s.md"
    src.write_text("# Title\n\n## Section A\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    doc = tmp_path / "t.docx"
    subprocess.run(["pandoc", str(src), "-o", str(doc)], check=True)
    got = js(HANDLER, tmp_path / "cache", doc)
    assert got["other_tool"] is None and got["blocked"] is None and got["text_file"] is None
    text = got["doc"]["content"][0]["text"]
    head, body = text.split("\n\n", 1)
    cached = pathlib.Path(head.split("Cite lines as ")[1].split(":<line>")[0])
    assert cached.parent == tmp_path / "cache/pazras/convert"
    lines = cached.read_text().splitlines()
    assert body.split("\n")[:2] == lines[2:4], "offset 3 is the cache file's line 3"
    assert "## Section A" in lines and "| a | b |" in lines
