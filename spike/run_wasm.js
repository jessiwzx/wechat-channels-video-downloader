// SPIKE: 用微信官方 WASM 解密器验证 —— ground truth
// 用法: node run_wasm.js <key> <encrypted_prefix.bin>
const fs = require('fs');
const path = require('path');

const KEY = process.argv[2] || '1522607660';
const ENC = process.argv[3] || path.join(__dirname, 'encrypted_prefix.bin');

// ---- 浏览器环境桩 ----
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.document = { title: '', currentScript: null };
globalThis.location = { href: 'https://res.wx.qq.com/' };
globalThis.VTS_WASM_URL = 'https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/1.3.0/wasm_video_decode.wasm';
globalThis.MAX_HEAP_SIZE = 33554432;

// ---- 官方 decrypt.js 的回调逻辑（含 reverse）----
globalThis.captured = null;     // reverse 后的密钥流（与页面行为一致）
globalThis.capturedRaw = null;  // reverse 前
globalThis.wasm_isaac_generate = function (ptr, len) {
  const heap = globalThis.__spikeModule.HEAPU8;
  const r = new Uint8Array(heap.buffer, ptr, len);
  globalThis.capturedRaw = Buffer.from(r);
  globalThis.captured = Buffer.from(r.reverse()); // decrypt.js: decryptor_array.set(r.reverse())
};

async function finish() {
  const M = globalThis.__spikeModule;
  try {
    console.log('runtime ready, WxIsaac64 =', typeof M.WxIsaac64);
    const dec = new M.WxIsaac64(KEY);
    dec.generate(131072);
    const captured = globalThis.captured;
    console.log('generate 完成, 密钥流长度:', captured && captured.length);
    fs.writeFileSync(path.join(__dirname, 'keystream_raw.bin'), globalThis.capturedRaw);
    fs.writeFileSync(path.join(__dirname, 'keystream_rev.bin'), captured);

    const enc = fs.readFileSync(ENC);
    const n = Math.min(enc.length, captured.length);
    const out = Buffer.allocUnsafe(n);
    for (let i = 0; i < n; i++) out[i] = enc[i] ^ captured[i];
    const head = out.subarray(0, 32);
    console.log('解密头(hex):', head.toString('hex'));
    console.log('解密头(ascii):', JSON.stringify(head.toString('latin1')));
    const ok = ['ftyp', 'moov', 'mdat', 'free', 'styp'].some((m) => out.subarray(0, 64).includes(m));
    console.log(ok ? '✓✓✓ MP4 特征检测成功 ✅' : '✗ 未检出 MP4 特征');
    process.exit(ok ? 0 : 1);
  } catch (e) {
    console.error('失败:', e);
    process.exit(3);
  }
}

globalThis.__spikeModule = {
  wasmBinary: fs.readFileSync(path.join(__dirname, 'wasm_video_decode.wasm')),
  print: (...a) => console.log('[wasm]', ...a),
  printErr: (...a) => console.error('[wasm-err]', ...a),
  onAbort: (e) => { console.error('ABORT', e); process.exit(2); },
  onRuntimeInitialized: finish,
};

// 胶水代码 `var Module = ...` 因 var 提升遮蔽全局，打补丁让它直接用我们的对象
let glue = fs.readFileSync(path.join(__dirname, 'wasm_video_decode.js'), 'utf8');
const decl = 'var Module = typeof Module !== \'undefined\' ? Module : {};';
if (!glue.includes(decl)) { console.error('找不到 Module 声明行'); process.exit(5); }
glue = glue.replace(decl, 'var Module = globalThis.__spikeModule;');
(0, eval)(glue);

setTimeout(() => {
  if (globalThis.captured) return;
  const M = globalThis.__spikeModule;
  console.error('超时：未触发 generate; WxIsaac64:', typeof M.WxIsaac64,
                '| HEAPU8:', typeof M.HEAPU8);
  process.exit(4);
}, 20000);
