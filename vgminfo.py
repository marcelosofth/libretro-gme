import sys, zipfile, gzip, struct

def show(name, data):
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    if data[:4] != b'Vgm ':
        return
    u = lambda o: struct.unpack_from('<I', data, o)[0]
    ver = u(8)
    start = 0x34 + u(0x34) if ver >= 0x150 else 0x40
    chips = []
    for nome, off in (('YM2203', 0x44), ('YM2151', 0x30), ('YM2612', 0x2C),
                      ('YM2413', 0x10), ('SN76489', 0x0C), ('SegaPCM', 0x38)):
        if off + 4 <= start and u(off) & 0x3FFFFFFF:
            chips.append('%s=%d' % (nome, u(off) & 0x3FFFFFFF))
    seg = u(0x18) / 44100.0
    print('%-32s v%x  %6.1fs  %s' % (name[:32], ver, seg, ' '.join(chips)))

for arq in sys.argv[1:]:
    if arq.lower().endswith('.zip'):
        z = zipfile.ZipFile(arq)
        for n in sorted(z.namelist()):
            show(n, z.read(n))
    else:
        show(arq, open(arq, 'rb').read())
