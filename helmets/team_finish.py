"""main.dol patch for NCAA Football 2005 (GameCube, USA): per-team helmet finish (gloss / matte / chrome).

How the game picks the helmet shine: the player-appearance code sets swap group 3 ("EnvMap") of the player model to
the helmet type (player+3808) at 0x802464a4 and 0x80246710. The patch adds three small hooks:

  hook 1  0x802f5454  (team -> uniform lookup, right after the team's TOID is fetched): remember TOID
  hook 2  0x8005a824  (start of the per-side uniform setup, r3 = side 0/1): remember TOID for that side
  hook 3  0x802464a4, 0x80246710  (EnvMap option = helmet type): look up the player's side -> team -> finish
          matte  -> option 255 (no shine pass)
          chrome -> option helmet+4 (the "Chr*" options added to the player models: shine pass drawn twice)
          gloss  -> unchanged

Code + data live in a new DOL text section at 0x80001800 (the low-memory area left free for debuggers).
FIN table: 512 bytes, one per team TOID (0 gloss, 1 matte, 2 chrome).

Needs the helmet pack v2 player models in PLADATA.DAT (they carry the extra "Chr*" EnvMap options); without them
chrome teams fall back to no shine pass at all. Install the helmet pack first.

Command line:
    python helmets/team_finish.py show main.dol
    python helmets/team_finish.py set main.dol main_new.dol 12=matte 40=chrome 7=gloss
"""
import struct

BASE = 0x80001800
MAGIC = b'HFIN\x00\x00\x00\x01'
LAST = BASE + 0x08
SIDE = BASE + 0x0C
FIN = BASE + 0x20
NFIN = 512
CODE = FIN + NFIN
HOOKS = {0x802f5454: (0x7c7e1b78, 'stub1'), 0x8005a824: (0x48279ff5, 'stub2'),
         0x802464a4: (0x88bf0ee0, 'stub3'), 0x80246710: (0x88bf0ee0, 'stub3')}
PLAYERS_PTR_OFF = -31764   # r13-relative pointer to the 22 on-field player records (5440 bytes each)
PLAYER_SIZE = 5440


# --- tiny PowerPC assembler -----------------------------------------------------------------------------------
def _d(op, d, a, imm): return (op << 26) | (d << 21) | (a << 16) | (imm & 0xFFFF)
def addi(d, a, i): return _d(14, d, a, i)
def li(d, i): return addi(d, 0, i)
def lis(d, i): return _d(15, d, 0, i)
def lwz(d, off, a): return _d(32, d, a, off)
def stw(s, off, a): return _d(36, s, a, off)
def lbz(d, off, a): return _d(34, d, a, off)
def andi_(a, s, i): return _d(28, s, a, i)
def cmpwi(a, i): return _d(11, 0, a, i)
def cmplwi(a, i): return _d(10, 0, a, i)
def _x(s, a, b, xo): return (31 << 26) | (s << 21) | (a << 16) | (b << 11) | (xo << 1)
def lwzx(d, a, b): return _x(d, a, b, 23)
def stwx(s, a, b): return _x(s, a, b, 151)
def lbzx(d, a, b): return _x(d, a, b, 87)
def mr(a, s): return _x(s, a, s, 444)
def cmpw(a, b): return _x(0, a, b, 0)
def mtctr(s): return (31 << 26) | (s << 21) | (9 << 16) | (467 << 1)
def slwi(a, s, n): return (21 << 26) | (s << 21) | (a << 16) | (n << 11) | (0 << 6) | ((31 - n) << 1)
def blr(): return 0x4E800020
def bclr(bo, bi): return (19 << 26) | (bo << 21) | (bi << 16) | (16 << 1)
def ha(x): return ((x >> 16) + (1 if x & 0x8000 else 0)) & 0xFFFF
def lo(x): return x & 0xFFFF


class Asm:
    def __init__(self, org):
        self.org = org; self.w = []; self.labels = {}; self.fix = []
    @property
    def pc(self): return self.org + 4 * len(self.w)
    def label(self, n): self.labels[n] = self.pc
    def __call__(self, *ws): self.w.extend(ws)
    def bc(self, bo, bi, target): self.fix.append((len(self.w), 'bc', bo, bi, target)); self.w.append(0)
    def b(self, target, lk=0): self.fix.append((len(self.w), 'b', lk, 0, target)); self.w.append(0)
    def done(self):
        for i, kind, x, y, t in self.fix:
            tgt = self.labels.get(t, t)
            disp = tgt - (self.org + 4 * i)
            if kind == 'bc':
                assert -0x8000 <= disp < 0x8000
                self.w[i] = (16 << 26) | (x << 21) | (y << 16) | (disp & 0xFFFC)
            else:
                assert -0x2000000 <= disp < 0x2000000
                self.w[i] = (18 << 26) | (disp & 0x3FFFFFC) | x
        return b''.join(struct.pack('>I', w) for w in self.w)


def build_code():
    a = Asm(CODE)
    # stub1: replaces "mr r30,r3" after the TOID lookup in the team->uniform query
    a.label('stub1')
    a(mr(30, 3), lis(12, ha(LAST)), stw(3, lo(LAST), 12), blr())
    # stub2: replaces "bl 0x802d4818" at the start of the per-side uniform setup; r3 = side
    a.label('stub2')
    a(lis(12, ha(LAST)), lwz(11, lo(LAST), 12), andi_(0, 3, 1), slwi(0, 0, 2),
      lis(12, ha(SIDE)), addi(12, 12, lo(SIDE)), stwx(11, 12, 0))
    a.b(0x802d4818)
    # stub3: replaces "lbz r5,3808(r31)" where the EnvMap option is chosen
    a.label('stub3')
    a(lbz(5, 3808, 31), lwz(12, PLAYERS_PTR_OFF, 13), cmpwi(12, 0))
    a(bclr(12, 2))                                    # beqlr  (no player table)
    a(li(11, 22), mtctr(11))
    a.label('loop')
    a(lwz(0, 4, 12), cmpw(0, 31))
    a.bc(12, 2, 'found')                              # beq found
    a(addi(12, 12, PLAYER_SIZE))
    a.bc(16, 0, 'loop')                               # bdnz loop
    a(blr())
    a.label('found')
    a(lbz(11, 2, 12), andi_(11, 11, 1), slwi(11, 11, 2),
      lis(12, ha(SIDE)), addi(12, 12, lo(SIDE)), lwzx(11, 12, 11),
      cmplwi(11, NFIN - 1))
    a(bclr(12, 1))                                    # bgtlr  (unknown team)
    a(lis(12, ha(FIN)), addi(12, 12, lo(FIN)), lbzx(0, 12, 11),
      cmpwi(0, 1))
    a.bc(4, 2, 'notmatte')                            # bne
    a(li(5, 255), blr())
    a.label('notmatte')
    a(cmpwi(0, 2))
    a(bclr(4, 2))                                     # bnelr
    a(addi(5, 5, 4), blr())
    code = a.done()
    return code, {k: v for k, v in a.labels.items() if k.startswith('stub')}


def section_image(fin=None):
    code, labels = build_code()
    img = bytearray(CODE - BASE) + code
    img[0:8] = MAGIC
    t = bytes(fin) if fin is not None else bytes(NFIN)
    img[FIN - BASE:FIN - BASE + NFIN] = t
    while len(img) % 32: img.append(0)
    return bytes(img), labels


class Dol:
    def __init__(self, data):
        self.d = bytearray(data)
        self.off = list(struct.unpack('>18I', self.d[0:72]))
        self.addr = list(struct.unpack('>18I', self.d[72:144]))
        self.size = list(struct.unpack('>18I', self.d[144:216]))

    def a2f(self, a):
        for i in range(18):
            if self.size[i] and self.addr[i] <= a < self.addr[i] + self.size[i]:
                return self.off[i] + a - self.addr[i]
        raise KeyError(hex(a))

    def word(self, a): return struct.unpack('>I', self.d[self.a2f(a):self.a2f(a) + 4])[0]
    def put(self, a, w): struct.pack_into('>I', self.d, self.a2f(a), w)

    def patched_slot(self):
        for i in range(18):
            if self.addr[i] == BASE and self.size[i]:
                return i
        return None

    def write_header(self):
        struct.pack_into('>18I', self.d, 0, *self.off)
        struct.pack_into('>18I', self.d, 72, *self.addr)
        struct.pack_into('>18I', self.d, 144, *self.size)


def apply(dol_bytes, fin=None):
    """Return patched main.dol bytes. Re-applying just rewrites the FIN table."""
    D = Dol(dol_bytes)
    img, labels = section_image(fin)
    slot = D.patched_slot()
    if slot is None:
        for a, (orig, _) in HOOKS.items():
            if D.word(a) != orig:
                raise ValueError('main.dol does not match NCAA Football 2005 (USA) at %08x' % a)
        slot = next(i for i in range(7) if D.size[i] == 0)
        pos = (len(D.d) + 31) & ~31
        D.d.extend(b'\0' * (pos - len(D.d)))
        D.d.extend(img)
        D.off[slot], D.addr[slot], D.size[slot] = pos, BASE, len(img)
        D.write_header()
    else:
        p = D.off[slot]
        D.d[p:p + len(img)] = img
    for a, (_, stub) in HOOKS.items():
        disp = labels[stub] - a
        D.put(a, (18 << 26) | (disp & 0x3FFFFFC) | 1)   # bl stub
    return bytes(D.d)


def read_fin(dol_bytes):
    D = Dol(dol_bytes)
    slot = D.patched_slot()
    if slot is None: return None
    p = D.off[slot]
    if D.d[p:p + 8] != MAGIC: return None
    return list(D.d[p + FIN - BASE:p + FIN - BASE + NFIN])


FINISH_CODES = {'gloss': 0, 'matte': 1, 'chrome': 2}
FINISH_NAMES = {v: k for k, v in FINISH_CODES.items()}


def set_team_finishes(src, dst, finishes, log=print):
    """finishes: {team_id: 'gloss'|'matte'|'chrome'}; teams not listed keep their current value."""
    data = open(src, 'rb').read()
    cur = read_fin(data) or [0] * NFIN
    for t, f in finishes.items():
        t = int(t)
        if not 0 <= t < NFIN:
            raise ValueError('team id out of range: %d' % t)
        cur[t] = FINISH_CODES[f]
    out = apply(data, cur)
    import os
    tmp = dst + '.tmp'
    open(tmp, 'wb').write(out)
    os.replace(tmp, dst)
    log('wrote %s (%d teams matte, %d chrome)' % (dst, cur.count(1), cur.count(2)))
    return cur


def main(argv):
    import sys
    if len(argv) >= 2 and argv[0] == 'show':
        fin = read_fin(open(argv[1], 'rb').read())
        if fin is None:
            print('main.dol is not patched yet (every team uses its helmet type finish)')
            return 0
        for t, f in enumerate(fin):
            if f: print('team %3d  %s' % (t, FINISH_NAMES.get(f, f)))
        print('all other teams: gloss')
        return 0
    if len(argv) >= 3 and argv[0] == 'set':
        fin = {}
        for a in argv[3:]:
            k, v = a.split('=')
            fin[int(k)] = v.lower()
        set_team_finishes(argv[1], argv[2], fin)
        return 0
    print('usage:\n  team_finish.py show main.dol\n  team_finish.py set main.dol main_new.dol 12=matte 40=chrome ...')
    return 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
