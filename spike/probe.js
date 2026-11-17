(function () {
  // SPIKE 探针 v2：在页面内解析 finderH5ExtTransfer 的完整 resp_json，
  // 提取视频对象（url/token/key/标题/时间）+ media 全字段表，回传紧凑结果。
  // 注：本文件为 UTF-8，由 mitmproxy 以 <script> 注入页面，无 ASCII 限制。
  var seen = {};
  function rep(o) {
    try {
      fetch('/__probe_sink', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: JSON.stringify(o)
      }).catch(function () {});
    } catch (e) {}
  }
  function harvest(respJson) {
    try {
      var o = JSON.parse(respJson);
      var objs = [];
      (function walk(n) {
        if (!n || typeof n !== 'object') return;
        var d = n.object_desc || n.objectDesc;
        if (d && d.media && d.media.length) objs.push(n);
        else for (var k in n) walk(n[k]);
      })(o);
      objs.forEach(function (ob) {
        var desc = ob.object_desc || ob.objectDesc;
        (desc.media || []).forEach(function (m) {
          if (!m || !m.url) return;
          var sig = String(m.url).slice(0, 80);
          if (seen[sig]) return; // 同一 URL 只报一次
          seen[sig] = 1;
          var fields = {};
          for (var kk in m) {
            var v = String(m[kk]);
            fields[kk] = v.length > 500 ? v.slice(0, 500) + '…' : v;
          }
          var obFields = {};
          for (var ok in ob) {
            if (ok === 'object_desc' || ok === 'objectDesc') continue;
            var ov = String(ob[ok]);
            if (ov.length > 200) ov = ov.slice(0, 200) + '…';
            obFields[ok] = ov;
          }
          rep({
            k: 'video',
            url: m.url,
            url_token: m.url_token || m.urlToken || '',
            decode_key: m.decode_key || m.decodeKey || '',
            title: desc.description || '',
            media_fields: fields,
            object_fields: obFields
          });
        });
      });
    } catch (e) { rep({ k: 'harvest_err', e: String(e) }); }
  }
  function hookBridge() {
    var B = window.WeixinJSBridge;
    if (!B) return false;
    if (B.invoke && !B.__probe2__) {
      var I = B.invoke;
      B.__probe2__ = 1;
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
