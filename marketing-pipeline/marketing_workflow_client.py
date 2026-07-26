# Before running the sample:
#    pip install --pre azure-ai-projects>=2.0.0b1
#    pip install azure-identity

import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agentserver.responses.models import ResponseStreamEventType

from dotenv import load_dotenv
load_dotenv(override=True)


myEndpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
myWorkflow = os.getenv("AZURE_AI_WORKFLOW_NAME")

# product = """We are launching a cloud-based customer support platform designed for small and mid-sized e-commerce businesses.
# The product uses AI to automatically categorize support tickets, suggest responses to agents, and surface urgent issues in real time.
# It integrates with popular tools like Shopify, Zendesk, and Slack, and can be set up in under 30 minutes without technical knowledge.
# The main goal is to reduce response times, lower support costs, and improve customer satisfaction without hiring additional staff.
# """

def read_workflow_input(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        raise ValueError(f"Input file is empty: {path}")

    return text



project_client = AIProjectClient(
    endpoint=myEndpoint,
    credential=DefaultAzureCredential(),
)

with project_client:

    workflow = {
        "name": myWorkflow,
        "version": "2",
    }
    
    openai_client = project_client.get_openai_client()

    product = read_workflow_input("product.txt")

    conversation = openai_client.conversations.create()
    print(f"Created conversation (id: {conversation.id})")

    stream = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": workflow["name"], "type": "agent_reference"}},
        input=product,
        stream=True,
        metadata={"x-ms-debug-mode-enabled": "1"},
    )

    for event in stream:
        if event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DONE:
            print("\t", event.text)
        elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and event.item.type == "workflow_action":
            print(f"********************************\nActor - '{event.item.action_id}' :")
        elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and event.item.type == "workflow_action":
            print(f"Workflow Item '{event.item.action_id}' is '{event.item.status}' - (previous item was : '{event.item.previous_action_id}')")
        elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_DONE and event.item.type == "workflow_action":
            print(f"Workflow Item '{event.item.action_id}' is '{event.item.status}' - (previous item was: '{event.item.previous_action_id}')")
        elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DELTA:
            print(event.delta)
        else:
            print(f"Unknown event: {event}")

    openai_client.conversations.delete(conversation_id=conversation.id)
    print("Conversation deleted")
