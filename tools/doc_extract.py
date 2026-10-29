"""Minimal Word 97 (.doc) text extractor using olefile + FIB/clx piece table."""
import sys, io, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import olefile


def read_fib(word):
    wIdent, nFib = struct.unpack_from('<HH', word, 0)
    flags = struct.unpack_from('<H', word, 0x000A)[0]
    fWhichTblStm = (flags >> 9) & 1
    fcClx, lcbClx = struct.unpack_from('<II', word, 0x01A2)
    return nFib, fWhichTblStm, fcClx, lcbClx


def read_clx(tbl, fcClx, lcbClx):
    clx = tbl[fcClx:fcClx + lcbClx]
    i = 0
    while i < len(clx):
        clxt = clx[i]
        if clxt == 0x01:
            cb = struct.unpack_from('<H', clx, i + 1)[0]
            i += 3 + cb
        elif clxt == 0x02:
            lcb = struct.unpack_from('<I', clx, i + 1)[0]
            return clx[i + 5:i + 5 + lcb]
        else:
            raise ValueError(f'bad clxt {clxt} at {i}')
    raise ValueError('no pcdt')


def extract_text(word, tbl, nFib):
    nFib_v, which, fcClx, lcbClx = read_fib(word)
    plc = read_clx(tbl, fcClx, lcbClx)
    n = (len(plc) - 4) // 12
    cps = list(struct.unpack_from('<%dI' % (n + 1), plc, 0))
    pcd_off = 4 * (n + 1)
    out = []
    for k in range(n):
        fl, fc, prm = struct.unpack_from('<HIH', plc, pcd_off + k * 8)
        cpStart, cpEnd = cps[k], cps[k + 1]
        nchars = cpEnd - cpStart
        if nchars == 0:
            continue
        compressed = bool(fc & 0x40000000)
        fcv = fc & 0x3FFFFFFF
        if compressed:
            fcv = fcv // 2
            raw = word[fcv:fcv + nchars]
            s = raw.decode('cp1252', errors='replace')
        else:
            raw = word[fcv:fcv + nchars * 2]
            s = raw.decode('utf-16-le', errors='replace')
        out.append(s)
    return ''.join(out)


def main(path):
    ole = olefile.OleFileIO(path)
    print('STREAMS:', ole.listdir())
    word = ole.openstream('WordDocument').read()
    nFib, which, fcClx, lcbClx = read_fib(word)
    tblname = '1Table' if which else '0Table'
    print(f'nFib={nFib} table={tblname} fcClx={fcClx} lcbClx={lcbClx}')
    tbl = ole.openstream(tblname).read()
    text = extract_text(word, tbl, nFib)
    # normalize word control chars
    ctrl = {
        '\r': '\n', '\x07': '\t|CELL|\t', '\x0b': '\n', '\x0c': '\n[PAGEBREAK]\n',
        '\x13': '[FIELD:', '\x14': '|', '\x15': ']', '\x01': '[PIC]',
        '\x08': '', '\x1e': '-', '\x1f': '', '\x02': '', '\x05': '',
    }
    for k, v in ctrl.items():
        text = text.replace(k, v)
    print('=== TEXT ===')
    print(text)


if __name__ == '__main__':
    main(sys.argv[1])
