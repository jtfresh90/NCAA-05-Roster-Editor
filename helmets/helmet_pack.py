#!/usr/bin/env python3
"""
NCAA Football 2005 (GameCube) helmet pack + helmet finishes for PLADATA.DAT.

The pack replaces the four detailed player models in PLADATA.DAT (entries 7-10: pm2400 / pm1200 / pm600 / pm300)
with versions carrying three new helmet shells:

    std     Standard helmet ........ stock
    adams   Adams helmet slot ...... "Football Helmet" by ZionCaesar (CC-BY-4.0)
    schutt  Schutt helmet slot ..... "Helmet" by osha22 (CC-BY-4.0)
    revo    Revolution helmet slot . Speedflex, from "Buffalo Bills Helmet" by Exodusks (CC-BY-4.0),
                                     plus its facemask as the RevoG2B mask on the close-up model

Each helmet type can be given a finish:
    gloss   the game's normal shine (default)
    matte   the helmet's shine pass ("EnvMap" swap group) switched off
    chrome  the shine pass drawn twice for a stronger reflection
Logos, numbers and stickers are separate decal pieces that never get the shine pass, so they look the same on
every finish. The finish is per helmet type (all players wearing that helmet), not per team.

Command line:
    python3 helmets/helmet_pack.py install PLADATA.DAT PLADATA_new.DAT [--finish revo=matte schutt=chrome ...]
    python3 helmets/helmet_pack.py show PLADATA.DAT

Pure Python 3, no extra packages. Every other entry of the archive is copied byte-for-byte.
"""
import os
import sys
import struct
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, 'pack')
PLAYER_MODELS = (7, 8, 9, 10)
LOD_NAMES = {7: 'pm2400 (close-up)', 8: 'pm1200', 9: 'pm600', 10: 'pm300'}
STOCK_SHA1 = '463febde2bd8497ff253c0110ceda38f32089c78'  # NCAA Football 2005 (USA) PLADATA.DAT

SLOTS = {  # key: (Head/EnvMap option name, label)
    'std': ('HelmetStd', 'Standard (stock helmet)'),
    'adams': ('HelmetAdams', 'Adams slot - Football Helmet (ZionCaesar)'),
    'schutt': ('HelmetSchutt', 'Schutt slot - Helmet (osha22)'),
    'revo': ('HelmetRevo', 'Revolution slot - Speedflex'),
}
FINISHES = ('gloss', 'matte', 'chrome')


# ----------------------------------------------------------------------------------------------------------------
# TERF archive (PLADATA.DAT)
# ----------------------------------------------------------------------------------------------------------------
class Terf:
    """DIR1 = (offset, size) per entry, offsets relative to the DATA tag, 0x40 aligned; COMP = (codec, raw size)."""

    def __init__(self, path):
        self.path = path
        self.d = d = open(path, 'rb').read()
        if d[:4] != b'TERF':
            raise ValueError('not a TERF archive: %s' % path)
        self.n = struct.unpack('>H', d[14:16])[0]
        self.dir1, self.comp_off, self.data = d.find(b'DIR1'), d.find(b'COMP'), d.find(b'DATA')
        self.dirs = [struct.unpack('>II', d[self.dir1 + 8 + 8 * i:self.dir1 + 16 + 8 * i]) for i in range(self.n)]
        self.comps = [struct.unpack('>II', d[self.comp_off + 8 + 8 * i:self.comp_off + 16 + 8 * i]) for i in range(self.n)]

    def raw(self, i):
        o, s = self.dirs[i]
        return self.d[self.data + o:self.data + o + s]

    def sha1(self):
        return hashlib.sha1(self.d).hexdigest()

    def write(self, dst, replace):
        """replace: {entry: (codec, stored_bytes, raw_size)}. Layout identical to the original otherwise."""
        d = self.d
        dirs = list(self.dirs); comps = list(self.comps)
        head = bytearray(d[:self.data + 8]); body = bytearray()
        pos = min(o for o, s in dirs if s)
        for i in sorted(range(self.n), key=lambda i: (self.dirs[i][0], i)):
            o, s = self.dirs[i]
            if i in replace:
                typ, blob, usize = replace[i]; comps[i] = (typ, usize)
            elif s == 0:  # empty entries still take their own 0x40 slot
                pos = (pos + 0x3F) & ~0x3F; dirs[i] = (pos, 0); pos += 1
                continue
            else:
                blob = d[self.data + o:self.data + o + s]
            pos = (pos + 0x3F) & ~0x3F
            dirs[i] = (pos, len(blob))
            need = pos - 8
            if len(body) < need:
                body.extend(b'\0' * (need - len(body)))
            body[need:need + len(blob)] = blob
            pos += len(blob)
        body.extend(b'\0' * ((-(self.data + 8 + len(body))) % 0x40))
        for i in range(self.n):
            struct.pack_into('>II', head, self.dir1 + 8 + 8 * i, *dirs[i])
            struct.pack_into('>II', head, self.comp_off + 8 + 8 * i, *comps[i])
        out = head + body
        struct.pack_into('>I', out, self.data + 4, len(out) - self.data)
        tmp = dst + '.tmp'
        open(tmp, 'wb').write(out)
        os.replace(tmp, dst)
        return hashlib.sha1(out).hexdigest()


# ----------------------------------------------------------------------------------------------------------------
# TMdl swap table (which draw batches each helmet type uses)
# ----------------------------------------------------------------------------------------------------------------
class SwapTable:
    def __init__(self, b):
        self.b = bytearray(b)
        b = self.b
        if b[:4] != b'TMdl':
            raise ValueError('not a TMdl model')
        n = struct.unpack('>H', b[8:10])[0]
        swap = None
        for k in range(n):
            if b[16 + 16 * k:20 + 16 * k] == b'Swap':
                swap = struct.unpack('>I', b[20 + 16 * k:24 + 16 * k])[0]
        self.ng, self.G, self.O, self.L = struct.unpack('>4I', b[swap:swap + 16])
        self.nopt = (self.G - self.O) // 20  # option table sits right before the group table

    def option(self, group, name):
        b = self.b
        for g in range(self.ng):
            r = b[self.G + 20 * g:self.G + 20 * g + 20]
            if r[:16].split(b'\0')[0] != group.encode():
                continue
            fo = struct.unpack('>H', r[16:18])[0]
            for o in range(fo, fo + r[18]):
                rec = self.O + 20 * o
                if b[rec:rec + 16].split(b'\0')[0] == name.encode():
                    return rec
        return None

    def get(self, rec):
        ls, lc = struct.unpack('>HH', self.b[rec + 16:rec + 20])
        return [struct.unpack('>H', self.b[self.L + 2 * i:self.L + 2 * i + 2])[0] for i in range(ls, ls + lc)]

    def room(self, rec):
        """list slots an option owns = distance to the next option's list start"""
        ls = struct.unpack('>H', self.b[rec + 16:rec + 18])[0]
        later = [struct.unpack('>H', self.b[self.O + 20 * o + 16:self.O + 20 * o + 18])[0] for o in range(self.nopt)]
        later = [x for x in later if x > ls]
        return (min(later) - ls) if later else 1

    def put(self, rec, ids):
        ls = struct.unpack('>H', self.b[rec + 16:rec + 18])[0]
        assert len(ids) <= self.room(rec)
        for i, v in enumerate(ids):
            struct.pack_into('>H', self.b, self.L + 2 * (ls + i), v)
        struct.pack_into('>H', self.b, rec + 18, len(ids))


def set_finish(model, slot, finish):
    """Return the model bytes with that helmet type's shine pass set to the finish."""
    st = SwapTable(model)
    opt = SLOTS[slot][0]
    head, env = st.option('Head', opt), st.option('EnvMap', opt)
    if head is None or env is None:
        return bytes(st.b)  # this LOD has no shine pass for the helmet
    shell = st.get(head)
    room = st.room(env)
    ids = {'matte': [], 'gloss': shell, 'chrome': [shell[0], shell[0]]}[finish][:room]
    st.put(env, ids)
    return bytes(st.b)


def get_finish(model, slot):
    st = SwapTable(model)
    opt = SLOTS[slot][0]
    head, env = st.option('Head', opt), st.option('EnvMap', opt)
    if head is None or env is None:
        return None
    e = st.get(env)
    if not e:
        return 'matte'
    if len(e) > 1 and len(set(e)) == 1:
        return 'chrome'
    return 'gloss'


# ----------------------------------------------------------------------------------------------------------------
# Pack install / inspect
# ----------------------------------------------------------------------------------------------------------------
def _pack_meta():
    meta = {}
    for line in open(os.path.join(PACK, 'entries.txt')):
        e, typ, usize = map(int, line.split())
        meta[e] = (typ, usize)
    return meta


def install(src, dst, finishes=None, log=print):
    """Write dst = src with the helmet pack installed. finishes: {slot: finish}; anything other than all-gloss
    stores the four player models uncompressed (codec 0, which the game already uses for some models)."""
    finishes = {k: v for k, v in (finishes or {}).items() if v}
    for k, v in finishes.items():
        if k not in SLOTS or v not in FINISHES:
            raise ValueError('bad finish %s=%s' % (k, v))
    t = Terf(src)
    if t.sha1() != STOCK_SHA1:
        log('note: source PLADATA.DAT is not the stock USA file (it may already be patched); '
            'entries 7-10 are replaced either way, everything else is kept as-is')
    custom = any(v != 'gloss' for v in finishes.values())
    meta = _pack_meta()
    rep = {}
    for e in PLAYER_MODELS:
        if custom:
            m = open(os.path.join(PACK, 'entry%04d.bin' % e), 'rb').read()
            for slot, fin in finishes.items():
                m = set_finish(m, slot, fin)
            rep[e] = (0, m, len(m))
        else:
            rep[e] = (meta[e][0], open(os.path.join(PACK, 'entry%04d.lzh1' % e), 'rb').read(), meta[e][1])
    sha = t.write(dst, rep)
    log('wrote %s (sha1 %s)' % (dst, sha))
    return sha


def show(path):
    """{slot: finish} read from an installed PLADATA.DAT (None if it can't be told)."""
    t = Terf(path)
    meta = _pack_meta()
    out = {'installed': False}
    typ, _ = t.comps[7]
    if typ == 0:
        m = t.raw(7)
        st = SwapTable(m)
        out['installed'] = len(st.get(st.option('Head', 'HelmetRevo'))) == 1  # stock Revo lists shell + jaw
        for s in SLOTS:
            out[s] = get_finish(m, s)
    else:
        pack_blob = open(os.path.join(PACK, 'entry0007.lzh1'), 'rb').read()
        out['installed'] = t.raw(7) == pack_blob
        for s in SLOTS:
            out[s] = 'gloss'  # compressed models are either stock or the default-finish pack
    return out


def main(argv):
    if len(argv) < 2 or argv[0] not in ('install', 'show'):
        print(__doc__)
        return 1
    if argv[0] == 'show':
        r = show(argv[1])
        print('helmet pack installed:', r['installed'])
        for s, (_, label) in SLOTS.items():
            print('  %-7s %-45s %s' % (s, label, r[s]))
        return 0
    files = [a for a in argv[1:] if '=' not in a and a != '--finish']
    fin = {}
    for a in argv[1:]:
        if '=' in a:
            k, v = a.lower().split('=', 1)
            fin[k] = v
    if len(files) != 2:
        print(__doc__)
        return 1
    install(files[0], files[1], fin)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
