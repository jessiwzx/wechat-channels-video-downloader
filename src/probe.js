(function () {
  // 生产探针 v3（由 capture_addon.py 注入 channels.weixin.qq.com 页面壳）
  // 改进自 spike v2：
  //  - 按“对象”去重上报（v2 按 url 去重，同对象多 media 会拆散）
  //  - media 数组整条回传，嵌套对象(spec/hdr_spec/hls_spec/codec_info/media_cdn_info)
  //    用 JSON.stringify 保留（v2 打成 "[object Object]" 丢失了变体清单）
  //  - 只上报有 decode_key 的视频对象（直播回放 key 为空，下载不了）
  var sent = {};
  function rep(o) {
    try {
      fetch('/__probe_sink', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: JSON.stringify(o)
      }).catch(function () {});
    } catch (e) {}
  }
  function J(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'object') { try { return JSON.stringify(v); } catch (e) { return ''; } }
    return String(v);
  }
  function pickMedia(m) {
    return {
      url: String(m.url || ''),
      url_token: String(m.url_token || m.urlToken || ''),
      decode_key: String(m.decode_key || m.decodeKey || ''),
      file_size: J(m.file_size),
      md5sum: J(m.md5sum),
      width: J(m.width),
      height: J(m.height),
      video_play_len: J(m.video_play_len),
      media_type: J(m.media_type),
      spec: J(m.spec),
      hdr_spec: J(m.hdr_spec),
      hls_spec: J(m.hls_spec),
      codec_info: J(m.codec_info),
      media_cdn_info: J(m.media_cdn_info)
    };
  }
  function handleObject(ob, desc) {
    try {
      var media = desc.media || [];
      if (!media.length) return;
      var usable = [];
      media.forEach(function (m) {
        if (m && m.url && m.decode_key) usable.push(pickMedia(m));
      });
      if (!usable.length) return;
      var id = String(ob.id || desc.object_nonce_id || '');
      if (id && sent[id]) return;
      if (id) sent[id] = 1;
      rep({
        k: 'video3',
        v: 3,
        ts: Date.now(),
        object: {
          id: id,
          nickname: String(ob.nickname || ''),
          username: String(ob.username || ''),
          createtime: J(ob.createtime || desc.createtime),
          title: String(desc.description || '')
        },
        media: usable
      });
    } catch (e) {}
  }
  function harvest(respJson) {
    try {
      var o = JSON.parse(respJson);
      (function walk(n) {
        if (!n || typeof n !== 'object') return;
        var d = n.object_desc || n.objectDesc;
        if (d && d.media && d.media.length) handleObject(n, d);
        else for (var k in n) walk(n[k]);
      })(o);
    } catch (e) {}
  }
  function hookBridge() {
    var B = window.WeixinJSBridge;
    if (!B) return false;
    if (B.invoke && !B.__probe3__) {
      var I = B.invoke;
      B.__probe3__ = 1;
      B.invoke = function (n, d, cb) {
        if (typeof cb === 'function') {
          arguments[2] = function (res) {
            try {
              if (n === 'finderH5ExtTransfer' && res) {
                var rj = res.jsapi_resp && res.jsapi_resp.resp_json;
                if (typeof rj === 'string' && rj) harvest(rj);
              }
            } catch (e) {}
            return cb.apply(this, arguments);
          };
        }
        return I.apply(this, arguments);
      };
    }
    return true;
  }
  var t = 0;
  var iv = setInterval(function () {
    t++;
    if (hookBridge() || t > 200) clearInterval(iv);
  }, 300);
})();
