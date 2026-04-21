"""CLI + batch pipeline for the transpiler."""
from __future__ import annotations
import re
import time
from pathlib import Path

from .paths import PROJECT, DECOMPILED_DIR, IL2CPP_DUMP, PTR_DAT_MAP, MAPPING_FILE, TRANSPILED_DIR
from .mapping import Mapping
from .parser import Method, parse_file
from .emitter import emit_class, derive_package, simple_class_name


# Globally-scoped loaded mapping, reused by pool workers (initialized by pool initializer).
_WORKER_MAPPING: Mapping | None = None


def _worker_init(mapping_path: str, il2cpp_path: str, ptr_dat_map_path: str):
    global _WORKER_MAPPING
    _WORKER_MAPPING = Mapping.load(Path(mapping_path), Path(il2cpp_path), Path(ptr_dat_map_path))


_TOP_HEADER_RE = re.compile(rb'^//\s*Decompiled top-level class:\s*(.+?)\s*$', re.MULTILINE)


def transpile_one_file(args: tuple[str, str, str]) -> tuple[str, int, str | None]:
    """Process one .c file → write a single .java for the top-level class."""
    in_path_str, in_root, out_root = args
    in_path = Path(in_path_str)
    mapping = _WORKER_MAPPING
    assert mapping is not None, "worker init failed"
    try:
        with open(in_path, 'rb') as f:
            src_head = f.read(4096)
        m = _TOP_HEADER_RE.search(src_head)
        if not m:
            return (str(in_path.relative_to(in_root)), 0, None)
        top_class_fqn = m.group(1).decode('utf-8').strip()

        methods = parse_file(in_path)
        if not methods:
            return (str(in_path.relative_to(in_root)), 0, None)

        java = emit_class(top_class_fqn, methods, mapping)
        pkg = derive_package(top_class_fqn, mapping)
        sname = simple_class_name(top_class_fqn)
        sname_safe = re.sub(r'[^A-Za-z0-9_$]', '_', sname)
        pkg_folder = Path(*pkg.split('.')) if pkg else Path('.')
        out_path = Path(out_root) / pkg_folder / f'{sname_safe}.java'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(java)
            if not java.endswith('\n'):
                fh.write('\n')
        return (str(in_path.relative_to(in_root)), len(methods), None)
    except Exception as e:
        import traceback
        tb = traceback.format_exc(limit=3)
        return (str(in_path), 0, f'{type(e).__name__}: {e}\n{tb}')


def run_batch(in_root: Path, out_root: Path, workers: int = 16):
    """Walk all .c files under in_root, transpile in parallel, write to out_root mirror tree."""
    import multiprocessing as mp

    c_files = sorted(in_root.rglob('*.c'))
    print(f'Found {len(c_files)} .c files under {in_root}')
    out_root.mkdir(parents=True, exist_ok=True)

    args = [(str(p), str(in_root), str(out_root)) for p in c_files]

    start = time.time()
    total_methods = 0
    total_errors: list[tuple[str, str]] = []

    with mp.Pool(workers,
                 initializer=_worker_init,
                 initargs=(str(MAPPING_FILE), str(IL2CPP_DUMP), str(PTR_DAT_MAP))) as pool:
        for i, (rel, n_methods, err) in enumerate(pool.imap_unordered(transpile_one_file, args, chunksize=4), 1):
            total_methods += n_methods
            if err:
                total_errors.append((rel, err))
            if i % 500 == 0 or i == len(args):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(args) - i) / rate if rate > 0 else 0
                print(f'  {i}/{len(args)} files, {total_methods} methods, {len(total_errors)} errors, {rate:.0f}/s, ETA {eta:.0f}s')

    elapsed = time.time() - start
    print(f'\nDone in {elapsed:.1f}s: {len(args)} files, {total_methods} methods written to {out_root}')
    if total_errors:
        print(f'\n{len(total_errors)} errors:')
        for rel, err in total_errors[:10]:
            print(f'  {rel}: {err.splitlines()[0]}')
        if len(total_errors) > 10:
            print(f'  ... and {len(total_errors) - 10} more')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Transpile Ghidra-decompiled IL2CPP .c to Java')
    sub = parser.add_subparsers(dest='cmd', required=True)
    one = sub.add_parser('one', help='Transpile a single .c file; writes to the tree and prints to stdout')
    one.add_argument('path')
    one.add_argument('--out', dest='out_root', default=str(TRANSPILED_DIR),
                     help='Output root for the .java file (default: data/transpiled_tacticus)')
    one.add_argument('--no-write', action='store_true', help='Only print; do not write')
    batch = sub.add_parser('batch', help='Transpile all .c files in a directory tree')
    batch.add_argument('--in', dest='in_root', default=str(DECOMPILED_DIR))
    batch.add_argument('--out', dest='out_root', default=str(TRANSPILED_DIR))
    batch.add_argument('--workers', type=int, default=16)
    opts = parser.parse_args()

    if opts.cmd == 'one':
        mapping = Mapping.load(MAPPING_FILE, IL2CPP_DUMP, PTR_DAT_MAP)
        in_path = Path(opts.path)
        # Prefer the top-level-class header (what the batch uses) so output lands at the
        # same path as a batch run would produce.
        with open(in_path, 'rb') as f:
            src_head = f.read(4096)
        mh = _TOP_HEADER_RE.search(src_head)
        top_class_fqn = mh.group(1).decode('utf-8').strip() if mh else None
        methods = parse_file(in_path)
        by_class: dict[str, list[Method]] = {}
        for m in methods:
            by_class.setdefault(m.class_fqn, []).append(m)
        if top_class_fqn:
            java = emit_class(top_class_fqn, methods, mapping)
            print(java)
            if not opts.no_write:
                from .emitter import derive_package, simple_class_name
                pkg = derive_package(top_class_fqn, mapping)
                sname = simple_class_name(top_class_fqn)
                sname_safe = re.sub(r'[^A-Za-z0-9_$]', '_', sname)
                out_root = Path(opts.out_root)
                pkg_folder = Path(*pkg.split('.')) if pkg else Path('.')
                out_path = out_root / pkg_folder / f'{sname_safe}.java'
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, 'w', encoding='utf-8') as fh:
                    fh.write(java)
                    if not java.endswith('\n'):
                        fh.write('\n')
                print(f'\n[wrote {out_path}]')
        else:
            for class_fqn, ms in by_class.items():
                print(emit_class(class_fqn, ms, mapping))
                print()
    elif opts.cmd == 'batch':
        run_batch(Path(opts.in_root), Path(opts.out_root), opts.workers)


if __name__ == '__main__':
    main()
