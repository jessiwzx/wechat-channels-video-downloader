# SPIKE: ISAAC-64 伪随机流生成器（视频号视频前 128KB XOR 解密用）
# 严格逐行移植自 nobiyou/wx_channel pkg/decrypt/decrypt.go（源头为微信官方 WASM 逆向）
# 注意三处易错点：mix() 是减法型 Jenkins 混合；isAAC64 的移位常数 21/5/12/33；
# ISAacRandom 从 Seed[255] 倒序消费，取尽后重新生成一轮。
import struct

GOLDEN = 0x9E3779B97F4A7C13
M = 0xFFFFFFFFFFFFFFFF


class RandCtx64:
    __slots__ = ("seed", "mm", "aa", "bb", "cc", "randcnt")

    def __init__(self, key: int):
        self.seed = [0] * 256
        self.mm = [0] * 256
        self.aa = 0
        self.bb = 0
        self.cc = 0
        self.randcnt = 255
        self._rand64_init(key & M)
        self._isAAC64()

    # ---- mix(a..h)：Go mix() 的直译 ----
    @staticmethod
    def _mix(s):
        a, b, c, d, e, f, g, h = s
        a = (a - e) & M
        f ^= h >> 9
        h = (h + a) & M
        b = (b - f) & M
        g ^= (a << 9) & M
        a = (a + b) & M
        c = (c - g) & M
        h ^= b >> 23
        b = (b + c) & M
        d = (d - h) & M
        a ^= (c << 15) & M
        c = (c + d) & M
        e = (e - a) & M
        b ^= d >> 14
        d = (d + e) & M
        f = (f - b) & M
        c ^= (e << 20) & M
        e = (e + f) & M
        g = (g - c) & M
        d ^= f >> 17
        f = (f + g) & M
        h = (h - d) & M
        e ^= (g << 14) & M
        g = (g + h) & M
        s[0:] = [a, b, c, d, e, f, g, h]

    def _rand64_init(self, key: int):
        self.seed[0] = key
        s = [GOLDEN] * 8
        for _ in range(4):
            self._mix(s)
        mm = self.mm
        for i in range(0, 256, 8):
            s[0] = (s[0] + self.seed[i]) & M
            s[1] = (s[1] + self.seed[i + 1]) & M
            s[2] = (s[2] + self.seed[i + 2]) & M
            s[3] = (s[3] + self.seed[i + 3]) & M
            s[4] = (s[4] + self.seed[i + 4]) & M
            s[5] = (s[5] + self.seed[i + 5]) & M
            s[6] = (s[6] + self.seed[i + 6]) & M
            s[7] = (s[7] + self.seed[i + 7]) & M
            self._mix(s)
            mm[i:i + 8] = s[:]
        for i in range(0, 256, 8):
            s[0] = (s[0] + mm[i]) & M
            s[1] = (s[1] + mm[i + 1]) & M
            s[2] = (s[2] + mm[i + 2]) & M
            s[3] = (s[3] + mm[i + 3]) & M
            s[4] = (s[4] + mm[i + 4]) & M
            s[5] = (s[5] + mm[i + 5]) & M
            s[6] = (s[6] + mm[i + 6]) & M
            s[7] = (s[7] + mm[i + 7]) & M
            self._mix(s)
            mm[i:i + 8] = s[:]

    def _isAAC64(self):
        self.cc = (self.cc + 1) & M
        self.bb = (self.bb + self.cc) & M
        mm, seed = self.mm, self.seed
        aa, bb = self.aa, self.bb
        for i in range(256):
            m = i & 3
            if m == 0:
                aa = (~(aa ^ ((aa << 21) & M))) & M
            elif m == 1:
                aa ^= aa >> 5
            elif m == 2:
                aa ^= (aa << 12) & M
            else:
                aa ^= aa >> 33
            aa = (aa + mm[(i + 128) & 255]) & M
            x = mm[i]
            y = (mm[(x >> 3) & 255] + aa + bb) & M
            mm[i] = y
            bb = (mm[(y >> 11) & 255] + x) & M
            seed[i] = bb
        self.aa, self.bb = aa, bb

    def random(self) -> int:
        result = self.seed[self.randcnt]
        if self.randcnt == 0:
            self._isAAC64()
            self.randcnt = 255
        else:
            self.randcnt -= 1
        return result


def decrypt_prefix(data: bytearray, enc_len: int, key: int) -> bytearray:
    """原地把 data[0:enc_len] 与 ISAAC-64 密钥流异或（大端 8 字节/步）"""
    ctx = RandCtx64(key)
    n = 0
    while n < enc_len:
        ks = struct.pack(">Q", ctx.random())
        for j in range(8):
            if n + j >= enc_len:
                break
            data[n + j] ^= ks[j]
        n += 8
    return data


def keystream(seed: int, length: int) -> bytes:
    out = bytearray()
    ctx = RandCtx64(seed)
    while len(out) < length:
        out += struct.pack(">Q", ctx.random())
    return bytes(out[:length])
