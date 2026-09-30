import assert from "node:assert/strict";
import {decideSnapshotRefresh,findActiveCollector} from "./transit-freshness-watchdog.mjs";
const now=Date.parse("2026-09-30T12:00:00Z");
const snap=(m,ready=true)=>({generated_at:new Date(now-m*60000).toISOString(),ready,health:{status:"watch"}});
assert.deepEqual(decideSnapshotRefresh(snap(10),now).wake,false);
assert.deepEqual(decideSnapshotRefresh(snap(38),now).wake,false);
assert.deepEqual(decideSnapshotRefresh(snap(40),now).reason,"COLLECTOR_OVERDUE");
assert.deepEqual(decideSnapshotRefresh(snap(120),now).wake,true);
assert.deepEqual(decideSnapshotRefresh(snap(2,false),now).reason,"SNAPSHOT_NOT_READY");
assert.deepEqual(decideSnapshotRefresh({generated_at:null,ready:true},now).reason,"INVALID_OR_FUTURE_SNAPSHOT");
assert.deepEqual(decideSnapshotRefresh({generated_at:new Date(now+6*60000).toISOString(),ready:true},now).wake,true);
assert.equal(findActiveCollector([{status:"completed",created_at:new Date(now-50*60000).toISOString()}],now),null);
assert.equal(findActiveCollector([{id:10,status:"in_progress",created_at:new Date(now-5*60000).toISOString()}],now).id,10);
assert.throws(()=>findActiveCollector([{id:20,status:"queued",created_at:new Date(now-21*60000).toISOString()}],now),/stuck/);
assert.throws(()=>findActiveCollector(null,now),/Unverifiable/);
// A temporarily missing operator must never be represented as full confidence.
assert.equal(decideSnapshotRefresh(snap(8),now).wake,false);
console.log("PASS transit watchdog freshness, missing data, active-run dedupe and stuck-run alerts");
