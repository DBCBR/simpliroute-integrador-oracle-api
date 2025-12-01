import sys
import os
import re


def looks_like_mojibake(s: str) -> bool:
    # heuristic: presence of common mojibake sequences like Ã©, Ã¡, Ã£, Â
    return bool(re.search(r'Ã[\w\W]|Â', s))


def fix_file(path: str) -> bool:
    """Try to detect mojibake or non-utf8 and rewrite file as UTF-8.
    Returns True if file was rewritten.
    """
    with open(path, 'rb') as f:
        b = f.read()

    try:
        text = b.decode('utf-8')
        if looks_like_mojibake(text):
            # try cp1252
            try:
                text_cp = b.decode('cp1252')
                # backup and write
                bak = path + '.bak'
                if not os.path.exists(bak):
                    os.rename(path, bak)
                with open(path, 'w', encoding='utf-8') as wf:
                    wf.write(text_cp)
                return True
            except Exception:
                return False
        else:
            # utf-8 and looks fine
            return False
    except UnicodeDecodeError:
        # not utf-8 at all: try cp1252
        try:
            text_cp = b.decode('cp1252')
            bak = path + '.bak'
            if not os.path.exists(bak):
                os.rename(path, bak)
            with open(path, 'w', encoding='utf-8') as wf:
                wf.write(text_cp)
            return True
        except Exception:
            return False


def try_fix_mojibake_by_transcoding(path: str) -> bool:
    with open(path, 'rb') as f:
        b = f.read()
    try:
        text = b.decode('utf-8')
    except Exception:
        try:
            text = b.decode('cp1252')
        except Exception:
            return False

    if not looks_like_mojibake(text):
        return False

    # attempt to fix by treating text as latin-1 bytes reinterpreted as utf-8
    try:
        fixed = text.encode('latin-1').decode('utf-8')
        if not looks_like_mojibake(fixed):
            bak = path + '.bak'
            if not os.path.exists(bak):
                os.rename(path, bak)
            with open(path, 'w', encoding='utf-8') as wf:
                wf.write(fixed)
            return True
    except Exception:
        pass
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python fix_input_encoding.py <file>')
        sys.exit(2)
    path = sys.argv[1]
    ok = fix_file(path)
    if ok:
        print('fixed:', path)
    else:
        print('no change needed or could not fix:', path)
