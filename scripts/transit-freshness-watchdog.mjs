// Independent schedule watchdog. GitHub scheduled collection is best-effort;
// check the committed snapshot, then wake the existing collector only when stale.
import {readFile} from "node:fs/promises";
import {pathToFileURL} from "node:url";

export function decideSnapshotRefresh(health,now=Date.now(),maxAgeMinutes=39){
  const t=Date.parse(health?.generated_at||"");
  if(!Number.isFinite(t)||t>now+5*60000)
    return {wake:true,reason:"INVALID_OR_FUTURE_SNAPSHOT",age_minutes:null};
  const age=Math.max(0,(now-t)/60000);
  if(health?.ready!==true)
    return {wake:true,reason:"SNAPSHOT_NOT_READY",age_minutes:age};
  return {wake:age>maxAgeMinutes,reason:age>maxAgeMinutes?"COLLECTOR_OVERDUE":"COLLECTOR_CURRENT",age_minutes:age};
}
export function findActiveCollector(runs,now=Date.now()){
  if(!Array.isArray(runs))throw Error("Unverifiable collector run inventory");
  const active=runs.filter(r=>r.status!=="completed");
  if(!active.length)return null;
  const newest=active.sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at))[0];
  const created=Date.parse(newest.created_at||"");
  if(!Number.isFinite(created)||now-created>20*60000)
    throw Error("Transit collector run is stuck or its timestamp is invalid; investigate before dispatching again");
  return newest;
}
async function main(){
  const health=JSON.parse(await readFile("data/health.json","utf8"));
  const decision=decideSnapshotRefresh(health);
  console.log("Transit freshness",JSON.stringify(decision));
  if(!decision.wake)return;
  const repo=process.env.GITHUB_REPOSITORY;
  const token=process.env.TRANSIT_ACTIONS_TOKEN;
  if(repo!=="kenzuko/transit-jotrip"||!token)
    throw Error("Fail closed: current Transit repository or Actions token missing");
  const root="https://api.github.com/repos/"+repo+"/actions/workflows/update-transit.yml";
  const headers={Authorization:"Bearer "+token,Accept:"application/vnd.github+json",
    "X-GitHub-Api-Version":"2022-11-28","User-Agent":"jotrip-transit-watchdog"};
  const list=await fetch(root+"/runs?per_page=12",{headers,signal:AbortSignal.timeout(12000)});
  if(!list.ok)throw Error("Cannot verify collector state: HTTP "+list.status);
  const payload=await list.json();
  const active=findActiveCollector(payload.workflow_runs);
  if(active){console.log("Existing collector still active:",active.id);return;}
  const result=await fetch(root+"/dispatches",{
    method:"POST",headers,body:JSON.stringify({ref:"main"}),signal:AbortSignal.timeout(12000)});
  if(result.status!==204)throw Error("Transit collector dispatch failed: HTTP "+result.status);
  console.log("Woke existing Transit collector after overdue/invalid snapshot");
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)
  main().catch(err=>{console.error("TRANSIT_FRESHNESS_WATCHDOG_FAILED:",err.message);process.exitCode=1});
