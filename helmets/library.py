"""NCAA 05 helmet library: put any of the library helmets into any of the game's four helmet slots and the library
facemasks into the 14 facemask options, in pure Python (no numpy).

Library data (helmets/library/):
    base/entry0007.bin .. entry0010.bin   the four player models, decoded (stock)
    helmets/<helmet>_<entry>.json         ready-made draw batches for one helmet on one model LOD
    masks/<FaceMask option>.json          a facemask for that option (close-up model only)
The TMdl helpers below are the same ones the build tools use (tmdl_write.py)."""
import os
import json
import base64
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, 'library')
ENTRIES = (7, 8, 9, 10)
SLOT_ORDER = ('std', 'adams', 'schutt', 'revo')          # EnvMap order; the Chr* options follow in the same order
SLOT_HEAD = {'std': 'HelmetStd', 'adams': 'HelmetAdams', 'schutt': 'HelmetSchutt', 'revo': 'HelmetRevo'}
SLOT_INNER = {'std': 'HelmetInnerStd', 'adams': 'HelmetInnerAdam', 'schutt': 'HelmetInnerSchu', 'revo': 'HelmetInnerRevo'}
CHR = {'std': 'ChrStd', 'adams': 'ChrAdams', 'schutt': 'ChrSchutt', 'revo': 'ChrRevo'}
HELMETS = {  # key: (label, credit)
    'speedflex': ('Riddell SpeedFlex style', 'modelled from product photos'),
    'axiom': ('Riddell Axiom style', 'modelled from product photos'),
    'f7': ('Schutt F7 style', 'modelled from product photos'),
    'air_xp': ('Schutt Air XP style', 'modelled from product photos'),
    'zero2': ('VICIS Zero2 style', 'modelled from product photos'),
    'shadow_xr': ('Xenith Shadow XR style', 'modelled from product photos'),
    'gladiator': ('LIGHT Gladiator style', 'modelled from product photos'),
}
DEFAULT_SLOTS = {'std': 'speedflex', 'adams': 'zero2', 'schutt': 'f7', 'revo': 'axiom'}


def available_helmets():
    d = os.path.join(LIB, 'helmets')
    have = {f.rsplit('_', 1)[0] for f in os.listdir(d)} if os.path.isdir(d) else set()
    return [h for h in HELMETS if h in have] + sorted(have - set(HELMETS))


def available_masks():
    d = os.path.join(LIB, 'masks')
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            j = json.load(open(os.path.join(d, f)))
            out[j['option']] = j['label']
    return out


def _dec_batch(j):
    return dict(template=base64.b64decode(j['template']), mat=j['mat'], dl=base64.b64decode(j['dl']), f3=j['f3'], f4=j['f4'],
                arrays=[dict(a, data=base64.b64decode(a['data'])) for a in j['arrays']])


def base_model(entry):
    return open(os.path.join(LIB, 'base', 'entry%04d.bin' % entry), 'rb').read()


def assemble(entry, slots, masks=True):
    """slots: {slot: helmet key or None (stock)}. Returns the TMdl bytes for that LOD."""
    b = base_model(entry)
    newb, edits = [], {}
    for slot in SLOT_ORDER:
        h = slots.get(slot)
        if not h:
            continue
        j = json.load(open(os.path.join(LIB, 'helmets', '%s_%d.json' % (h, entry))))
        off = len(newb)
        newb += [_dec_batch(x) for x in j['batches']]
        for key, refs in j['edits'].items():
            grp, opt = key.split('|')
            opt = {'HelmetStd': SLOT_HEAD[slot], 'HelmetInnerStd': SLOT_INNER[slot]}.get(opt, opt)
            edits[(grp, opt)] = [('new', r[1] + off) if isinstance(r, list) else r for r in refs]
    sw, _ = swap_table(b)
    for slot in SLOT_ORDER:   # the new shells carry their own jaw: drop the stock pad piece of that slot
        if slots.get(slot) and ('HelmetPadPie', SLOT_HEAD[slot]) in sw and sw[('HelmetPadPie', SLOT_HEAD[slot])]['lc']:
            edits[('HelmetPadPie', SLOT_HEAD[slot])] = []
    if masks and entry == 7 and os.path.isdir(os.path.join(LIB, 'masks')):
        for f in sorted(os.listdir(os.path.join(LIB, 'masks'))):
            j = json.load(open(os.path.join(LIB, 'masks', f)))
            if ('FaceMask', j['option']) not in sw:
                continue
            newb.append(_dec_batch(j['batch']))
            edits[('FaceMask', j['option'])] = [('new', len(newb) - 1)]
    if newb:
        b, _ = add_batches(b, newb, edits)
    # chrome finish options (shine pass twice), one per slot, after the four helmet options
    sw, _ = swap_table(b)
    new_opts = []
    for slot in SLOT_ORDER:
        head = sw.get(('Head', SLOT_HEAD[slot]))
        if head and head['list'] and ('EnvMap', SLOT_HEAD[slot]) in sw and ('EnvMap', CHR[slot]) not in sw:
            s = head['list'][0]
            new_opts.append((CHR[slot], [s, s]))
    if new_opts:
        b, _ = add_group_options(b, 'EnvMap', new_opts)
    return b


# ---------------------------------------------------------------------------------------------------------------
# TMdl helpers (from tmdl_write.py)
# ---------------------------------------------------------------------------------------------------------------
def al(x, a=32):
    return (x + a - 1) // a * a


def _chunks(b):
    n = struct.unpack('>H', b[8:10])[0]
    out = {}
    for k in range(n):
        tag, off, size, flag = struct.unpack('>4sIII', b[16 + 16 * k:32 + 16 * k])
        out[tag.decode()] = (off, size, flag, 16 + 16 * k)
    return out


def swap_table(b):
    """{(group, option): dict(opt=index, rec=offset, ls=list start, lc=count, list=[...])} and the list base."""
    chunks = _chunks(b)
    s = chunks['Swap'][0]
    ng, G, O, L = struct.unpack('>4I', b[s:s + 16])
    out = {}
    for g in range(ng):
        r = b[G + 20 * g:G + 20 * g + 20]
        gn = r[:16].split(b'\0')[0].decode(); fo = struct.unpack('>H', r[16:18])[0]; c = r[18]
        for o in range(fo, fo + c):
            rr = b[O + 20 * o:O + 20 * o + 20]
            on = rr[:16].split(b'\0')[0].decode(); ls, lc = struct.unpack('>HH', rr[16:20])
            out[(gn, on)] = dict(opt=o, rec=O + 20 * o, ls=ls, lc=lc,
                                 list=[struct.unpack('>H', b[L + 2 * i:L + 2 * i + 2])[0] for i in range(ls, ls + lc)])
    return out, L


def add_batches(b, new_batches, swap_edits):
    """b: TMdl bytes. new_batches: list from build_batch. swap_edits: {(group, option): [batch refs]} where a ref is
    an int (existing batch) or ('new', k). The option's list is rewritten in place (it can only shrink or stay)."""
    b = bytearray(b)
    ch = _chunks(b)
    g_off, g_size, _, g_rec = ch['Geom']
    m_off, m_size, _, m_rec = ch['Matl']
    assert m_off >= g_off + g_size and m_off + m_size == len(b), 'unexpected chunk order'
    A, na, B, nb, cval = struct.unpack('>5I', b[g_off:g_off + 20])
    old_B = bytes(b[B:B + 12 * nb]); old_A = bytes(b[A:A + 24 * na])
    # --- build insertion blob, placed at ins (absolute) ---
    ins = al(g_off + g_size, 32)
    blob = bytearray()
    cache = {}
    def put(data, align=32, share=True):
        data = bytes(data)
        if share and data in cache: return cache[data]
        while (ins + len(blob)) % align: blob.append(0)
        o = ins + len(blob); blob.extend(data)
        if share: cache[data] = o
        return o
    new_arr_recs = []; new_bat_recs = []
    for k, nbt in enumerate(new_batches):
        astart = nb + len(new_arr_recs)
        for a in nbt['arrays']:
            off = put(a['data'])
            new_arr_recs.append(struct.pack('>IHBBBBBB', off, a['count'], a['attr'], a['stride'], a['cnt'], a['typ'], a['frac'], a['x']))
        dlo = put(nbt['dl'])
        r = bytearray(nbt['template'])
        struct.pack_into('>IHH', r, 0, dlo, len(nbt['dl']) // 32, nbt['mat'])
        struct.pack_into('>HHH', r, 10, nbt['f3'], nbt['f4'], astart)
        r[16] = len(nbt['arrays'])
        new_bat_recs.append(bytes(r))
    newB = put(old_B + b''.join(new_arr_recs), share=False)
    newA = put(old_A + b''.join(new_bat_recs), share=False)
    geom_end = ins + len(blob)
    new_m_off = al(geom_end, 32)
    while ins + len(blob) < new_m_off: blob.append(0)
    delta = new_m_off - m_off
    matl = bytearray(b[m_off:m_off + m_size])
    for i in range(0, m_size - 3, 4):
        w = struct.unpack('>I', matl[i:i + 4])[0]
        if m_off <= w < m_off + m_size:
            struct.pack_into('>I', matl, i, w + delta)
    out = bytearray(b[:ins]) + blob + matl
    # headers
    struct.pack_into('>5I', out, g_off, newA, na + len(new_batches), newB, nb + len(new_arr_recs), cval)
    struct.pack_into('>I', out, g_rec + 8, geom_end - g_off)
    struct.pack_into('>I', out, m_rec + 4, new_m_off)
    struct.pack_into('>I', out, 4, len(out))
    # swaps
    sw, L = swap_table(bytes(out))
    for key, refs in swap_edits.items():
        e = sw[key]
        ids = [na + r[1] if isinstance(r, tuple) else r for r in refs]
        assert len(ids) <= e['lc'], (key, 'list can only shrink in place')
        for i, v in enumerate(ids):
            struct.pack_into('>H', out, L + 2 * (e['ls'] + i), v)
        struct.pack_into('>H', out, e['rec'] + 18, len(ids))
    return bytes(out), [na + k for k in range(len(new_batches))]


def _relocate_after(out, start, delta):
    """All chunks at/after `start` were moved by `delta`: fix chunk table + every absolute pointer inside them."""
    n = struct.unpack('>H', out[8:10])[0]
    ch = {}
    for k in range(n):
        tag, off, size, flag = struct.unpack('>4sIII', out[16 + 16 * k:32 + 16 * k])
        if off >= start:
            off += delta
            struct.pack_into('>I', out, 16 + 16 * k + 4, off)
        ch[tag.decode()] = (off, size)
    if 'Clst' in ch and ch['Clst'][0] >= start + delta:
        c = ch['Clst'][0]
        p = struct.unpack('>I', out[c:c + 4])[0]
        if p: struct.pack_into('>I', out, c, p + delta)
    if 'Geom' in ch and ch['Geom'][0] >= start + delta:
        g = ch['Geom'][0]
        A, na, B, nb = struct.unpack('>4I', out[g:g + 16])
        A += delta; B += delta
        struct.pack_into('>I', out, g, A); struct.pack_into('>I', out, g + 8, B)
        for k in range(nb):
            o = struct.unpack('>I', out[B + 12 * k:B + 12 * k + 4])[0]
            struct.pack_into('>I', out, B + 12 * k, o + delta)
        for k in range(na):
            o = struct.unpack('>I', out[A + 24 * k:A + 24 * k + 4])[0]
            if o: struct.pack_into('>I', out, A + 24 * k, o + delta)
    if 'Matl' in ch and ch['Matl'][0] >= start + delta:
        m, ms = ch['Matl']
        old_lo, old_hi = m - delta, m - delta + ms
        for i in range(m, m + ms - 3, 4):
            w = struct.unpack('>I', out[i:i + 4])[0]
            if old_lo <= w < old_hi:
                struct.pack_into('>I', out, i, w + delta)
    struct.pack_into('>I', out, 4, len(out))


def add_group_options(b, group, new_opts):
    """Append options to a swap group. new_opts: list of (name, [batch ids]). Grows the Swap chunk in place and
    shifts/relocates everything after it. Returns new bytes and the new options' indices within the group."""
    b = bytearray(b)
    ch = _chunks(b)
    s, ssize, _, srec = ch['Swap']
    ng, G, O, L = struct.unpack('>4I', b[s:s + 16])
    nopt = (G - O) // 20
    lists = [struct.unpack('>H', b[L + 2 * i:L + 2 * i + 2])[0] for i in range((O - L) // 2)]
    opts = [bytearray(b[O + 20 * o:O + 20 * o + 20]) for o in range(nopt)]
    grps = [bytearray(b[G + 20 * g:G + 20 * g + 20]) for g in range(ng)]
    gi = next(g for g in range(ng) if grps[g][:16].split(b'\0')[0] == group.encode())
    fo = struct.unpack('>H', grps[gi][16:18])[0]; cnt = grps[gi][18]
    ins = fo + cnt
    new_recs = []
    for name, ids in new_opts:
        r = bytearray(20); r[:len(name)] = name.encode()[:12]
        struct.pack_into('>HH', r, 16, len(lists), len(ids))
        lists += ids; new_recs.append(r)
    opts = opts[:ins] + new_recs + opts[ins:]
    for g in range(ng):
        f = struct.unpack('>H', grps[g][16:18])[0]
        if g != gi and f >= ins: struct.pack_into('>H', grps[g], 16, f + len(new_recs))
    grps[gi][18] = cnt + len(new_recs)
    L2 = s + 16
    O2 = L2 + 2 * len(lists); O2 = (O2 + 3) & ~3
    G2 = O2 + 20 * len(opts)
    body = bytearray(struct.pack('>4I', ng, G2, O2, L2))
    body += b''.join(struct.pack('>H', x) for x in lists)
    body += b'\0' * (O2 - (s + len(body)))
    body += b''.join(opts) + b''.join(grps)
    old_end = s + ssize
    nxt = min(v[0] for k, v in ch.items() if v[0] >= old_end)
    room = nxt - s
    need = len(body)
    delta = 0 if need <= room else ((need - room + 31) // 32) * 32
    out = bytearray(b[:s]) + body + b'\0' * (room + delta - need) + b[nxt:]
    struct.pack_into('>I', out, srec + 8, need)
    if delta:
        _relocate_after(out, nxt, delta)
    return bytes(out), list(range(cnt, cnt + len(new_recs)))

