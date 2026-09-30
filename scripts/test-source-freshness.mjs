import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
const js=readFileSync("app.js","utf8"),html=readFileSync("index.html","utf8");
const start=js.indexOf("function sourceFreshnessNote("),end=js.indexOf("function statusTone(",start);
assert(start>=0&&end>start);
const note=vm.runInNewContext(js.slice(start,end)+"\nsourceFreshnessNote",{Intl,Date});
const example={phu_quoc_express:{status:"cached",last_success_at:"2026-09-30T08:58:46+07:00"},
 superdong:{status:"empty"}};
const shown=note(example);
assert.match(shown,/Phú Quốc Express.*lịch lưu.*08:58/s);
assert.match(shown,/Superdong.*không có nghĩa hãng ngừng chạy/);
assert.equal(note({phu_quoc_express:{status:"ok"},superdong:{status:"ok"}}),"");
assert.match(note({phu_quoc_express:{status:"error"},superdong:{status:"error"}}),/cần xác nhận trực tiếp/);
assert.match(js,/sourceFreshnessNote\(d\.sources\?\.registry\)/);
assert.match(js,/https:\/\/openphuquoc\.com\/bus\//);
assert.doesNotMatch(js,/https:\/\/cms\.openphuquoc\.com\/bus\//);
assert.match(html,/app\.js\?v=20260930-source-freshness1/);
console.log("Transit source-specific freshness and canonical guide QA PASS");
