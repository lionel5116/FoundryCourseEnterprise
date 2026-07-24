# Before running the sample:
#    pip install --pre azure-ai-projects>=2.0.0b1
#    pip install azure-identity

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from dotenv import load_dotenv
import os

load_dotenv(override=True)

myEndpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
myAgent = os.getenv("AZURE_AI_AGENT_NAME")

project_client = AIProjectClient(
    endpoint=myEndpoint,
    credential=DefaultAzureCredential(),
)

# Get an existing agent
agent = project_client.agents.get(agent_name=myAgent)
print(f"Retrieved agent: {agent.name}")

openai_client = project_client.get_openai_client()

customer_query = "Hi, I was charged twice for my subscription this month. This is really frustrating. Can you please check what happened?"

# Reference the agent to get a response
response = openai_client.responses.create(
    input=[{"role": "user", "content": customer_query}],
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)

print(f"Response output: {response.output_text}")



