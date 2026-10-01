const REPOSITORY = "kenzuko/transit-jotrip";
const EVENT_TYPE = "transit_refresh";
const SNAPSHOT_URL = "https://raw.githubusercontent.com/kenzuko/transit-jotrip/main/data/health.json";
const MAX_AGE_MINUTES = 39;
const COOLDOWN_MINUTES = 15;

const json = (body, status = 200) => new Response(JSON.stringify(body, null, 2), {
  status,
  headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store"
  }
});

const ageMinutes = (value, now = Date.now()) => {
  const t = Date.parse(value || "");
  return Number.isFinite(t) ? Math.max(0, (now - t) / 60000) : null;
};

const transitRuns = value => Array.isArray(value?.workflow_runs)
  ? value.workflow_runs.filter(run => run?.name === "Update Transit Snapshot")
  : [];

export function decideWake(snapshot, inventory = {}, now = Date.now()) {
  const observedAt = snapshot?.generated_at || null;
  const age = ageMinutes(observedAt, now);

  if (age !== null && age <= MAX_AGE_MINUTES) {
    return { wake: false, reason: "SNAPSHOT_CURRENT", observed_at: observedAt, age_minutes: age };
  }

  const runs = transitRuns(inventory);
  const active = runs.find(run => ["queued", "in_progress"].includes(run?.status));
  if (active) {
    return {
      wake: false,
      reason: "COLLECTOR_ACTIVE",
      observed_at: observedAt,
      age_minutes: age,
      run_id: active.id || null
    };
  }

  const recent = runs
    .map(run => ({ run, created: Date.parse(run?.created_at || "") }))
    .filter(item => Number.isFinite(item.created))
    .sort((a, b) => b.created - a.created)[0];

  if (recent && now - recent.created < COOLDOWN_MINUTES * 60000) {
    return {
      wake: false,
      reason: "RECENT_COLLECTOR_COOLDOWN",
      observed_at: observedAt,
      age_minutes: age,
      run_id: recent.run.id || null
    };
  }

  return {
    wake: true,
    reason: age === null ? "SNAPSHOT_TIME_UNVERIFIABLE" : "SNAPSHOT_OVERDUE",
    observed_at: observedAt,
    age_minutes: age
  };
}

async function fetchSnapshot(fetcher = fetch) {
  const response = await fetcher(SNAPSHOT_URL + "?wake_check=" + Date.now(), {
    headers: {
      accept: "application/json",
      "cache-control": "no-cache"
    }
  });
  if (!response.ok) {
    throw new Error("Snapshot HTTP " + response.status);
  }
  const body = await response.json();
  if (!body || body.schema_version !== "transit-health-v1") {
    throw new Error("Unexpected Transit health schema");
  }
  return body;
}

async function githubJson(fetcher, url, token, init = {}) {
  const response = await fetcher(url, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: "Bearer " + token,
      "x-github-api-version": "2022-11-28",
      "user-agent": "jotrip-transit-wake",
      ...(init.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error("GitHub " + response.status + " " + body.slice(0, 180));
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function runWake(env = {}, {
  fetcher = fetch,
  now = Date.now()
} = {}) {
  let snapshot;
  try {
    snapshot = await fetchSnapshot(fetcher);
  } catch (error) {
    return {
      status: "NO_ACTION",
      wake: false,
      reason: "SNAPSHOT_CHECK_FAILED",
      error: String(error?.message || error)
    };
  }

  const age = ageMinutes(snapshot.generated_at, now);
  if (age !== null && age <= MAX_AGE_MINUTES) {
    return {
      status: "NO_ACTION",
      wake: false,
      reason: "SNAPSHOT_CURRENT",
      observed_at: snapshot.generated_at,
      age_minutes: age
    };
  }

  const token = String(env.GITHUB_TRANSIT_WAKE_TOKEN || "").trim();
  if (!token) {
    return {
      status: "DISABLED_MISSING_CREDENTIAL",
      wake: false,
      reason: "GITHUB_TRANSIT_WAKE_TOKEN_MISSING",
      observed_at: snapshot.generated_at || null,
      age_minutes: age
    };
  }

  const base = "https://api.github.com/repos/" + REPOSITORY;
  const inventory = await githubJson(fetcher, base + "/actions/runs?per_page=20", token);
  const decision = decideWake(snapshot, inventory, now);
  if (!decision.wake) {
    return { status: "NO_ACTION", ...decision };
  }

  await githubJson(fetcher, base + "/dispatches", token, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      event_type: EVENT_TYPE,
      client_payload: {
        source: "jotrip-transit-wake",
        reason: decision.reason
      }
    })
  });

  return {
    status: "DISPATCHED",
    ...decision,
    repository: REPOSITORY,
    event_type: EVENT_TYPE
  };
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil((async () => {
      try {
        const result = await runWake(env);
        console.log("Transit wake", JSON.stringify(result));
      } catch (error) {
        console.error("Transit wake failed", String(error?.stack || error));
      }
    })());
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/health") {
      return json({ error: "not_found" }, 404);
    }
    return json({
      status: "ok",
      service: "jotrip-transit-wake",
      role: "scheduler_only",
      repository: REPOSITORY,
      event_type: EVENT_TYPE,
      max_age_minutes: MAX_AGE_MINUTES,
      cooldown_minutes: COOLDOWN_MINUTES,
      credential_bound: Boolean(String(env.GITHUB_TRANSIT_WAKE_TOKEN || "").trim()),
      now: new Date().toISOString()
    });
  }
};
