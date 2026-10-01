import test from "node:test";
import assert from "node:assert/strict";
import { decideWake, runWake } from "../cloudflare/transit-wake-worker.js";

const NOW = Date.parse("2026-10-01T04:00:00Z");
const snapshot = minutes => ({
  schema_version: "transit-health-v1",
  generated_at: new Date(NOW - minutes * 60000).toISOString()
});

const snapshotResponse = body => new Response(JSON.stringify(body), {
  status: 200,
  headers: { "content-type": "application/json" }
});

test("fresh snapshot requires no GitHub credential or API call", async () => {
  const calls = [];
  const out = await runWake({}, {
    now: NOW,
    fetcher: async url => {
      calls.push(String(url));
      return snapshotResponse(snapshot(10));
    }
  });
  assert.equal(out.status, "NO_ACTION");
  assert.equal(out.reason, "SNAPSHOT_CURRENT");
  assert.equal(calls.length, 1);
});

test("overdue snapshot fails closed without isolated credential", async () => {
  const out = await runWake({}, {
    now: NOW,
    fetcher: async () => snapshotResponse(snapshot(80))
  });
  assert.equal(out.status, "DISABLED_MISSING_CREDENTIAL");
  assert.equal(out.reason, "GITHUB_TRANSIT_WAKE_TOKEN_MISSING");
});

test("active collector suppresses duplicate dispatch", () => {
  const decision = decideWake(snapshot(80), {
    workflow_runs: [{
      id: 11,
      name: "Update Transit Snapshot",
      status: "in_progress",
      created_at: "2026-10-01T03:58:00Z"
    }]
  }, NOW);
  assert.equal(decision.wake, false);
  assert.equal(decision.reason, "COLLECTOR_ACTIVE");
});

test("recent completed collector enforces cooldown", () => {
  const decision = decideWake(snapshot(80), {
    workflow_runs: [{
      id: 12,
      name: "Update Transit Snapshot",
      status: "completed",
      conclusion: "success",
      created_at: "2026-10-01T03:52:00Z"
    }]
  }, NOW);
  assert.equal(decision.wake, false);
  assert.equal(decision.reason, "RECENT_COLLECTOR_COOLDOWN");
});

test("overdue snapshot dispatches existing Transit collector exactly once", async () => {
  const calls = [];
  const out = await runWake({ GITHUB_TRANSIT_WAKE_TOKEN: "test-token" }, {
    now: NOW,
    fetcher: async (url, init = {}) => {
      calls.push({ url: String(url), method: init.method || "GET", body: init.body || null });
      if (String(url).includes("raw.githubusercontent.com")) {
        return snapshotResponse(snapshot(80));
      }
      if ((init.method || "GET") === "GET") {
        return new Response(JSON.stringify({
          workflow_runs: [{
            id: 13,
            name: "Update Transit Snapshot",
            status: "completed",
            conclusion: "success",
            created_at: "2026-10-01T02:00:00Z"
          }]
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      assert.match(String(url), /\/dispatches$/);
      const body = JSON.parse(init.body);
      assert.equal(body.event_type, "transit_refresh");
      assert.equal(body.client_payload.source, "jotrip-transit-wake");
      return new Response(null, { status: 204 });
    }
  });

  assert.equal(out.status, "DISPATCHED");
  assert.equal(calls.filter(call => call.method === "POST").length, 1);
});

test("snapshot fetch failure never dispatches blindly", async () => {
  let calls = 0;
  const out = await runWake({ GITHUB_TRANSIT_WAKE_TOKEN: "test-token" }, {
    now: NOW,
    fetcher: async () => {
      calls += 1;
      return new Response("upstream down", { status: 503 });
    }
  });
  assert.equal(out.status, "NO_ACTION");
  assert.equal(out.reason, "SNAPSHOT_CHECK_FAILED");
  assert.equal(calls, 1);
});

test("GitHub authorization failure is visible", async () => {
  await assert.rejects(
    runWake({ GITHUB_TRANSIT_WAKE_TOKEN: "bad-token" }, {
      now: NOW,
      fetcher: async url => {
        if (String(url).includes("raw.githubusercontent.com")) {
          return snapshotResponse(snapshot(80));
        }
        return new Response("forbidden", { status: 403 });
      }
    }),
    /GitHub 403/
  );
});
