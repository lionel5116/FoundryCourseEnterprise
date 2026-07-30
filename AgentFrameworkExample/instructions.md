# Fixes to agent_framework_example.py

The script was written against an older version of the `agent-framework` API.
The version installed in `.myvenv` (`agent-framework 1.12.1`) has moved/renamed
several of the symbols it used. Here's what changed:

## 1. `FoundryChatClient` import path

```diff
- from agent_framework.azure import FoundryChatClient
+ from agent_framework.foundry import FoundryChatClient
```

`FoundryChatClient` lives in the `agent_framework.foundry` subpackage
(from the `agent-framework-foundry` distribution), not `agent_framework.azure`.

## 2. `FoundryChatClient` constructor kwarg

```diff
  chat_client = FoundryChatClient(
      project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
-     model_deployment_name=MODEL_DEPLOYMENT,
+     model=MODEL_DEPLOYMENT,
      credential=credential,
  )
```

The constructor's keyword argument for the deployment/model name is `model`,
not `model_deployment_name`.

## 3. `ChatAgent` → `Agent`

```diff
- from agent_framework import ChatAgent, SequentialBuilder
+ from agent_framework import Agent
+ from agent_framework.orchestrations import SequentialBuilder
```

```diff
  generator = Agent(
-     chat_client=chat_client,
+     chat_client,
      name="title-description-generator",
      instructions="...",
  )
```

`ChatAgent` no longer exists. The current class is `Agent`, and it takes the
chat client as a **positional** argument (`client`), not a `chat_client=`
keyword.

## 4. `SequentialBuilder` location and API

`SequentialBuilder` moved to the `agent_framework.orchestrations` subpackage
and its API changed from a fluent `.participants(...)` call to a constructor
keyword argument:

```diff
- workflow = SequentialBuilder().participants([generator, refiner]).build()
+ workflow = SequentialBuilder(participants=[generator, refiner]).build()
```

## 5. `result.get_final_output()` doesn't exist

`WorkflowRunResult` (returned by `await workflow.run(...)`) has no
`get_final_output()` method. Use `get_outputs()`, which returns a list of
`AgentResponse` objects (one per participant selected via `output_from`; by
default just the last participant in a `SequentialBuilder` chain). Pull the
text off the last one:

```diff
- draft = result.get_final_output()
+ draft = result.get_outputs()[-1].text
```

This fix was applied at both call sites (the initial run and the
feedback/regenerate run).

## Verification

- Confirmed via `dir()` inspection of the installed packages that
  `agent_framework.foundry.FoundryChatClient`, `agent_framework.Agent`, and
  `agent_framework.orchestrations.SequentialBuilder` exist and match the
  signatures used above.
- Constructed a `FoundryChatClient`, two `Agent`s, and built the
  `SequentialBuilder` workflow end-to-end with dummy credentials/endpoint to
  confirm the object graph wires up without error (network calls were not
  exercised).

## Note

If this course's materials are pinned to an older `agent-framework` version,
consider checking `requirements.txt` / `pyproject.toml` for a version pin —
the API surface used in the original script matches an earlier release than
the `1.12.1` currently installed in `.myvenv`.
