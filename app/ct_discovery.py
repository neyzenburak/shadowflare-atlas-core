"""Find a user-owned table in the selected game folder, without executing it."""
from pathlib import Path
from ct_table import MAX_BYTES


def discover(folder):
    """Inspect only top-level files; never fetch a table or scan other folders."""
    return sorted((p for p in Path(folder).iterdir() if p.suffix.lower()=='.ct' and p.is_file()),key=lambda p:p.name.casefold())


def read_local_file(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('CT dosyası 4 MB sınırını aşamaz.')
    with path.open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    if not 0<len(raw)<=MAX_BYTES:raise ValueError('CT dosyası 4 MB sınırını aşamaz.')
    return raw
