"""
attach_a2a_tool.py

Attaches the oracle-fusion-hub agent to customer-support-agent as an A2A tool,
using the Foundry REST API / SDK directly — this bypasses the "Select a tool"
dialog in the portal, which was greying out the Agent2Agent (A2A) option
regardless of model selection.

WHAT THIS DOES
1. Creates (or reuses) a project connection of category "RemoteA2A" that points
   at the oracle-fusion-hub agent's A2A endpoint, authenticated via the calling
   agent's own Entra Agent Identity (AgenticIdentityToken) — appropriate since
   both agents live in the same Foundry project.
2. Creates a NEW VERSION of customer-support-agent that includes BOTH the
   File Search tool and the A2A tool, on top of your existing model +
   instructions.

FIXES IN THIS VERSION (vs. your last run)
- Adds agent_card_path="agentCard/v1.0" to the A2A tool. Foundry-hosted
  agents serve their card at this custom path, NOT the A2A spec default of
  /.well-known/agent-card.json — that mismatch is what caused the
  "Failed to fetch agent card: 404" error in the Playground.
- Re-adds the File Search tool alongside A2A. create_version() replaces the
  tools list rather than merging it, so the previous run (which only passed
  the A2A tool) silently dropped File Search from the new version.

BEFORE YOU RUN THIS
- pip install azure-ai-projects azure-identity requests python-dotenv --upgrade
- az login (account needs Contributor/Owner on the Foundry resource)
- Confirm your .env has: FOUNDRY_ACCOUNT_NAME, PROJECT_NAME, RESOURCE_GROUP,
  SUBSCRIPTION_ID, A2A_CONNECTION_NAME, AZURE_AI_AGENT_NAME,
  AZURE_AI_MODEL_DEPLOYMENT_NAME
- Add FILE_SEARCH_VECTOR_STORE_ID below (or as an env var) — set it to the
  vector store ID your File Search tool currently uses, e.g. from the Tools
  panel: "2025-toyota-rav4-index" -> vs_uoDxsEA8bUUWio8Y3mfWLvLd. Confirm the
  exact ID in your own portal before running; don't trust this value blindly.
"""

import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    A2APreviewTool,
    FileSearchTool,
)
import requests

from dotenv import load_dotenv
load_dotenv(override=True)


# ----------------------- CONFIG: fill these in -----------------------------

FOUNDRY_ACCOUNT_NAME = os.getenv("FOUNDRY_ACCOUNT_NAME")
PROJECT_NAME = os.getenv("PROJECT_NAME")
RESOURCE_GROUP = os.getenv("RESOURCE_GROUP")
SUBSCRIPTION_ID = os.getenv("SUBSCRIPTION_ID")
A2A_CONNECTION_NAME = os.getenv("A2A_CONNECTION_NAME")
CUSTOMER_AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME")
MODEL_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")

# NEW: vector store ID for File Search, so it doesn't get dropped this time.
# Set FILE_SEARCH_VECTOR_STORE_ID in your .env, or hardcode it here.
FILE_SEARCH_VECTOR_STORE_ID = os.getenv(
    "FILE_SEARCH_VECTOR_STORE_ID", "vs_uoDxsEA8bUUWio8Y3mfWLvLd"
)  # TODO: confirm this matches the ID shown in the Tools panel

PROJECT_ENDPOINT = (
    f"https://{FOUNDRY_ACCOUNT_NAME}.services.ai.azure.com"
    f"/api/projects/{PROJECT_NAME}"
)

# The A2A endpoint you confirmed is live on oracle-fusion-hub
ORACLE_A2A_BASE_URL = (
    f"{PROJECT_ENDPOINT}/agents/oracle-fusion-hub/endpoint/protocols/a2a"
)

# Paste your EXACT current instructions here so the new version preserves them
CURRENT_INSTRUCTIONS = """
You are a professional customer support assistant operating in a strictly grounded environment.

You have two authoritative sources of information, and you must choose the correct one based on the topic of the user's question. You must never answer from your own general knowledge, prior training, or assumptions — every answer must come from one of these two tools.

1. Oracle Fusion questions: If the user asks about Oracle Fusion module access, deployments, timelines, Finance (AP/AR/GL/Cash), Budget & Planning (EPM), or Grants/Procurement/Travel & Expense, call the oracle-fusion-hub-a2a-connection tool and base your answer on its response.

2. All other questions: For everything else, use the File Search tool as your sole and authoritative source of information.

If a question doesn't clearly fall into either category, use File Search first. If File Search doesn't contain relevant information and the question could plausibly relate to Oracle Fusion, try the oracle-fusion-hub-a2a-connection tool before telling the user you don't have an answer.
""".strip()  # TODO: replace with your real instructions if this isn't exact

# -----------------------------------------------------------------------


def get_arm_token():
    cred = DefaultAzureCredential()
    return cred.get_token("https://management.azure.com/.default").token


def create_a2a_connection():
    """Create (or update) the RemoteA2A project connection via REST."""
    token = get_arm_token()
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{FOUNDRY_ACCOUNT_NAME}"
        f"/projects/{PROJECT_NAME}/connections/{A2A_CONNECTION_NAME}"
        f"?api-version=2025-04-01-preview"
    )
    body = {
        "tags": None,
        "location": None,
        "name": A2A_CONNECTION_NAME,
        "type": "Microsoft.MachineLearningServices/workspaces/connections",
        "properties": {
            "authType": "AgenticIdentityToken",
            "group": "ServicesAndApps",
            "category": "RemoteA2A",
            "expiryTime": None,
            "target": ORACLE_A2A_BASE_URL,
            "isSharedToAll": True,
            "sharedUserList": [],
            "audience": "https://ai.azure.com",
            "Credentials": {},
            "metadata": {"ApiType": "Azure"},
        },
    }
    resp = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    print(f"A2A connection '{A2A_CONNECTION_NAME}' created/updated.")
    return resp.json()


def attach_tool_to_agent():
    """Create a new version of customer-support-agent with File Search + A2A."""
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    a2a_connection = project.connections.get(A2A_CONNECTION_NAME)

    # DEBUG: print what the connection actually reports as its target. If
    # this doesn't match ORACLE_A2A_BASE_URL exactly, that mismatch is likely
    # the real cause of the "must target the same host, project, and agent"
    # error — possibly due to propagation lag between the ARM plane (used to
    # create the connection) and the Foundry project plane (used to read it
    # back here).
    connection_target = getattr(a2a_connection, "target", None)
    print(f"Connection target (as read back):  {connection_target}")
    print(f"Locally computed ORACLE_A2A_BASE_URL: {ORACLE_A2A_BASE_URL}")
    if connection_target and connection_target != ORACLE_A2A_BASE_URL:
        print("WARNING: these do not match. Building agent_card_path from "
              "the connection's own target instead, to guarantee they agree.")

    # Use whichever base URL the connection actually reports, falling back
    # to our locally computed one only if the SDK doesn't expose .target.
    effective_base_url = connection_target or ORACLE_A2A_BASE_URL

    a2a_tool = A2APreviewTool(
        project_connection_id=a2a_connection.id,
        agent_card_path=f"{effective_base_url}/agentCard/v0.3",
    )

    # FIX: re-include File Search so this version doesn't lose it again.
    # If this constructor signature errors, run:
    #   python -c "from azure.ai.projects.models import FileSearchTool; help(FileSearchTool)"
    # and adjust the args to match your installed SDK version.
    file_search_tool = FileSearchTool(vector_store_ids=[FILE_SEARCH_VECTOR_STORE_ID])

    agent = project.agents.create_version(
        agent_name=CUSTOMER_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_NAME,
            instructions=CURRENT_INSTRUCTIONS,
            tools=[file_search_tool, a2a_tool],
        ),
    )
    print(
        f"New version created: {agent.name} v{agent.version} "
        f"(id: {agent.id})"
    )
    print("Go to the Foundry portal, open this agent, and confirm the new "
          "version has BOTH File Search and the A2A tool before making it "
          "Active.")


if __name__ == "__main__":
    create_a2a_connection()
    attach_tool_to_agent()