import pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[2]
CANDIDATES = ['NewEngine/neocore2/third_party/joltc-sys/Cargo.toml.orig', 'NewEngine/neocore2/winit-early.log', 'tools/scripts/northstar_bridge/cli.py.forcewrite.bak', 'tools/scripts/northstar_bridge/console.py.bak', 'tools/scripts/northstar_bridge/server.py.bak', 'tools/scripts/takesome/suite/progress_frame.py.bak']

def delete_rel(rel, dry_run=False):
    p=(ROOT/rel).resolve()
    if not str(p).startswith(str(ROOT.resolve())):
        print(f"[SKIP] escapes root: {rel}"); return
    if not p.exists():
        print(f"[SKIP] missing: {rel}"); return
    if dry_run:
        print(f"[DRY] delete: {rel}"); return
    if p.is_dir(): shutil.rmtree(p)
    else: p.unlink()
    print(f"[OK] deleted: {rel}")

if __name__ == "__main__":
    import sys
    dry="--dry-run" in sys.argv
    for rel in CANDIDATES: delete_rel(rel,dry)
