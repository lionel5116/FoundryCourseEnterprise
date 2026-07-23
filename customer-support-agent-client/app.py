import os
import streamlit as st
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# ------------------------------------
# Streamlit setup
# ------------------------------------
st.set_page_config(page_title="Support Agent", page_icon="💬", layout="centered")
st.title("💬 Customer Support Agent (Foundry)")
st.write("Paste a customer ticket and get the agent's response.")

# ------------------------------------
# Load env (.env optional)
# ------------------------------------
load_dotenv()

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME") or os.getenv("AZURE_EXISTING_AGENT_NAME") or os.getenv("AZURE_EXISTING_AGENT_ID")

# IMPORTANT: if someone accidentally set AGENT_NAME to "customer-support-agent:2"
# normalize it back to the real name by stripping anything after ":".
if AGENT_NAME and ":" in AGENT_NAME:
    AGENT_NAME = AGENT_NAME.split(":")[0]

if not PROJECT_ENDPOINT or not AGENT_NAME:
    st.error(
        "Please set the environment variables AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_AGENT_NAME (or AZURE_EXISTING_AIPROJECT_ENDPOINT and AZURE_EXISTING_AGENT_NAME) in your .env file."
    )
    st.stop()


if not AGENT_NAME:
    st.error(
        "Please set the environment variable AZURE_AI_AGENT_NAME (or AZURE_EXISTING_AGENT_NAME) in your .env file."
    )
    st.stop()

@st.cache_resource
def init_clients(project_endpoint: str, agent_name: str):
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # This expects the *agent name*, not an ID with :version
    agent = project_client.agents.get(agent_name=agent_name)
    openai_client = project_client.get_openai_client()

    return agent, openai_client

try:
    agent, openai_client = init_clients(PROJECT_ENDPOINT, AGENT_NAME)
except Exception as e:
    st.error("Failed to initialize Foundry agent client.")
    st.exception(e)
    st.stop()

st.caption(f"Project endpoint: `{PROJECT_ENDPOINT}`")
st.caption(f"Using agent: **{agent.name}**")


# ------------------------------------
# UI
# ------------------------------------
ticket = st.text_area(
    "Customer ticket",
    height=180,
    placeholder="Example:\nHi, I was charged twice for my subscription this month. Please help.",
)


if st.button("Send to agent", type="primary"):
    if not ticket.strip():
        st.warning("Please paste a ticket first.")
        st.stop()

    with st.spinner("Calling agent..."):
        try:
            response = openai_client.responses.create(
                input=[{"role": "user", "content": f"Customer message:\n{ticket.strip()}"}],
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            st.subheader("Agent output")
            st.text(response.output_text)
        except Exception as e:
            st.error("Failed to get response from agent.")
            st.exception(e)