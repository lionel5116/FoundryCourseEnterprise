# Connecting Oracle Fusion Hub to Customer Support Agent via A2A

## Summary

Goal: attach `oracle-fusion-hub` (a specialized Foundry agent) as an A2A tool
on `customer-support-agent`, so the latter can delegate Oracle Fusion
questions to it and return a synthesized answer.

The portal's UI blocked this at the "Select a tool" step (Agent2Agent (A2A)
stayed greyed out regardless of model). We worked around it using the
Foundry REST API / Python SDK directly, then debugged four separate issues
that surfaced only once the tool was actually wired up. End to end, this
took roughly 20 agent versions to resolve.

---

## Part 1 — Expose oracle-fusion-hub as an A2A endpoint

1. Opened `oracle-fusion-hub` → **Details** tab.
2. Under **Endpoints**, found **A2A protocol** showing only a **Set up**
   button (unlike Responses protocol, which was already Active).
3. Clicked **Set up** → filled out the **Create an agent card to set up A2A**
   dialog:
   - **Name**: `oracle-fusion-hub`
   - **Description**: rewritten to describe capability, not configuration —
     "Answers questions about Oracle Fusion module deployments, system
     access, timelines, and support during Toyota's Wave 1 transition,
     covering Finance, Budget & Planning, and Grants/Procurement."
   - **Agent skills** — added three, mirroring the agent's existing starter
     prompts:
     - **Finance Support** (tags: finance, AP, AR, GL, cash)
     - **Budget & Planning** (tags: EPM, budgeting, planning, Oracle EPM)
     - **Grants, Procurement & Travel** (tags: grants, projects, procurement,
       travel, expense)
     - Each skill included a description and 1–2 example prompts.
4. Saved. **A2A protocol** flipped to **Active**, with a live endpoint:
   `https://lionel-7414-resource.services.ai.azure.com/api/projects/lionel-7414/agents/oracle-fusion-hub/endpoint/protocols/a2a`

---

## Part 2 — Attempted to attach the A2A tool via the portal UI (blocked)

1. On `customer-support-agent` → Playground → Tools → **Add** → **Browse all
   tools** → **Custom** tab → **Agent2Agent (A2A)**.
2. Result: the option was greyed out with the tooltip *"This tool doesn't
   work with the model you selected. Please use another model."*
3. **Troubleshooting the model theory:**
   - Tried switching models. `gpt-4.1` and `gpt-4o` failed outright with
     `ServiceModelDeprecating` — both had entered Azure's "Deprecating"
     lifecycle stage (new deployments blocked ahead of their Oct 2026
     retirement dates), unrelated to A2A.
   - Deployed `gpt-5.1` instead (current GA replacement). A2A tool was
     **still greyed out** with the same message.
   - Tried multiple other models. All greyed out.
   - **Diagnostic check**: opened the tool picker again — **OpenAPI tool**
     and **MCP** were both fully clickable, only **Agent2Agent (A2A)** was
     disabled. This ruled out subscription/region/general-tooling issues —
     the block was specific to A2A, and not resolved by any model swap.
   - Conclusion: likely a portal-side bug or incomplete rollout of the A2A
     preview feature, not a real backend restriction (later confirmed —
     the API-level workaround succeeded where the UI did not).

---

## Part 3 — Workaround: attach the A2A tool via API/SDK

Since the portal blocked it but Microsoft's docs confirmed A2A is fully
supported via Python/C#/TypeScript/REST regardless of portal state, we
wrote `attach_a2a_tool.py` to:

1. **Create a project connection** (category `RemoteA2A`) pointing at
   oracle-fusion-hub's A2A endpoint, authenticated via
   `AgenticIdentityToken` (appropriate since both agents live in the same
   Foundry project).
2. **Create a new agent version** of `customer-support-agent` with the A2A
   tool attached via `A2APreviewTool(project_connection_id=...)`.

First run succeeded at the API level — connection created, new version
created — confirming the UI's greyed-out button was not a real backend
block.

---

## Part 4 — Bugs found and fixed during testing

### Bug 1: `create_version` replaces tools, doesn't merge

The first successful script run created a new agent version with **only**
the A2A tool. The agent's existing **File Search** tool (its main knowledge
source) silently disappeared, because `PromptAgentDefinition(tools=[...])`
replaces the entire tool list rather than appending to it.

**Fix:** explicitly re-include `FileSearchTool(vector_store_ids=[...])`
alongside the A2A tool in every `create_version` call:

```python
tools=[file_search_tool, a2a_tool]
```

### Bug 2: Conflicting instructions

The original instructions told the agent to treat File Search as the "sole
and authoritative source... for ALL user questions," which directly
contradicted a separate line asking it to call the Oracle Fusion Hub tool
for certain topics. Rewrote the instructions to give explicit, non-conflicting
routing logic: Oracle-related topics → A2A tool; everything else → File
Search; fallback order if ambiguous.

### Bug 3: Wrong agent card path (404, then a validation error)

Testing produced: *"Failed to fetch agent card: Response status code does
not indicate success: 404 (Not Found)."*

Foundry-hosted agents serve their agent card at a **custom path**, not the
A2A spec's default `/.well-known/agent-card.json`. Several attempts were
needed to find the right value:

- `agent_card_path="agentCard/v1.0"` (relative) → 404
- `agent_card_path=f"{base_url}/agentCard/v1.0"` (full URL) → new error:
  *"Agent card path must target the same host, project, and agent as the
  server URL."*
- `agent_card_path="agentCard/v0.3"` (relative, matching what Foundry's own
  generated sample code used for this exact agent) → **same** "must target"
  error as v1.0 full URL — ruling out the version tag as the cause.

**Root cause:** the connection was created via the Azure Resource Manager
plane (`management.azure.com`) but read back via the Foundry project plane
(`services.ai.azure.com`) — a possible propagation gap between the two,
producing a mismatch between the locally-computed base URL and what the
connection actually reported as its `target`.

**Fix:** derive `agent_card_path` directly from the connection object's own
`target` field (read back from the SDK) rather than recomputing it
independently, guaranteeing they always match:

```python
connection_target = getattr(a2a_connection, "target", None)
effective_base_url = connection_target or ORACLE_A2A_BASE_URL
a2a_tool = A2APreviewTool(
    project_connection_id=a2a_connection.id,
    agent_card_path=f"{effective_base_url}/agentCard/v0.3",
)
```

This cleared the validation error entirely.

### Bug 4: Genuine 404 — missing permissions (not a path problem)

After the fix above, a *different* 404 appeared: *"Failed to fetch agent
card: 404 (Not Found)"* — no longer a validation error, a real fetch
failure.

**Diagnosis:** ran a manual `curl` against the exact same URL, using the
developer's own `az` login token:

```bash
TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)
curl -i -H "Authorization: Bearer $TOKEN" \
  "https://lionel-7414-resource.services.ai.azure.com/api/projects/lionel-7414/agents/oracle-fusion-hub/endpoint/protocols/a2a/agentCard/v0.3"
```

This returned a full, valid `200 OK` agent card. **The endpoint and path
were correct all along.** The difference: the curl call used the
developer's own identity (broad access), while the live A2A tool call
authenticates as `customer-support-agent`'s own **Entra Agent Identity**,
which had never been granted any permission to call oracle-fusion-hub.
Azure API Management often reports unauthorized access as a 404 rather than
401/403, to avoid confirming a resource's existence to an unauthorized
caller — which is why this looked identical to the earlier path problem.

**Fix:** granted the **Foundry Agent Consumer** role
("Allows interacting with Foundry agents at runtime") to
`customer-support-agent`'s Entra Agent Identity, scoped to the
`lionel-7414-resource`. The Azure portal's role-assignment "Select members"
picker couldn't resolve the Entra Agent Identity by name or by pasting its
Object ID (a known portal limitation for this newer principal type), so the
assignment was done via Azure CLI instead:

```bash
az role assignment create \
  --assignee-object-id "e1fcf006-e9fc-494a-b2d7-ba1ab2fd3b69" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry Agent Consumer" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-lionel-6322/providers/Microsoft.CognitiveServices/accounts/lionel-7414-resource"
```

This succeeded immediately and returned a valid role assignment object.

### Bug 5 (not a bug): Rate limiting from repeated testing

After the permissions fix, one test hit: *"Your requests to gpt-5-mini for
gpt-5-mini in eastus2 have exceeded rate limit."* The deployment's quota was
50 requests/minute — easily exhausted by ~15 visible test messages, since
each one involves multiple backend calls (tool-routing decision, tool
execution, response synthesis), doubled further whenever the A2A call to
oracle-fusion-hub also spent quota against the same shared deployment.
Waiting ~1 minute for the rolling window to reset resolved it. No code or
config change needed; noted here in case it recurs — consider requesting a
quota increase via Foundry's Quotas page if iterative testing continues.

---

## Final working state

- `customer-support-agent` (Version 20) has both **File Search**
  (`2025-toyota-rav4-index`) and the **A2A tool**
  (`oracle-fusion-hub-a2a-connection`) attached together.
- Instructions clearly route Oracle Fusion topics to the A2A tool and
  everything else to File Search.
- `customer-support-agent`'s Entra Agent Identity has the **Foundry Agent
  Consumer** role on `lionel-7414-resource`, enabling it to call
  oracle-fusion-hub.
- Verified working in the Playground: asking about Oracle Fusion correctly
  triggers a clarifying/routing response referencing oracle-fusion-hub's
  defined skills.

## Next steps / open items

- **Confirm via Traces** that a specific Oracle question (e.g. "How do I
  request AP access?") actually invokes the `oracle-fusion-hub-a2a-connection`
  tool end to end, not just that the model talks about Oracle Fusion from
  its own reasoning.
- Version 20 is not yet Active — review it fully in the Playground before
  switching the version selector / publishing.
- Consider whether the Foundry Agent Consumer role should be scoped more
  narrowly (to the specific agent rather than the whole resource) once
  things are stable.
- If iterating further, consider requesting a quota increase on the
  gpt-5-mini deployment to avoid repeated rate-limit interruptions during
  testing.
- Worth reporting the original portal bug (A2A tool greyed out for all
  models) to Microsoft via the "Suggest a fix" link on the A2A docs page or
  the `microsoft-foundry` GitHub discussions, since the API-level workaround
  succeeding confirms it was a portal defect, not a real restriction.