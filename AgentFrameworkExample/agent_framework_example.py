import os
import asyncio
from azure.identity.aio import DefaultAzureCredential
from agent_framework.foundry import FoundryChatClient
from agent_framework import Agent
from agent_framework.orchestrations import SequentialBuilder

from dotenv import load_dotenv
load_dotenv(override=True)

FOUNDRY_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
MODEL_DEPLOYMENT = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")

async def main():
    credential = DefaultAzureCredential()

    # Underlying Foundry-backed chat client — shared across agents
    chat_client = FoundryChatClient(
        project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
        model=MODEL_DEPLOYMENT,
        credential=credential,
    )

    # Agent 1: generator
    generator = Agent(
        chat_client,
        name="title-description-generator",
        instructions="Generate a concise title and description from the given input.",
    )

    # Agent 2: refiner
    refiner = Agent(
        chat_client,
        name="title-description-quality-refiner",
        instructions="Critique and improve the title/description for clarity and tone.",
    )

    # This is the orchestration primitive: Sequential pattern
    # replaces the manual node-chaining you built in the portal Workflow
    workflow = SequentialBuilder(participants=[generator, refiner]).build()

    result = await workflow.run("Product: wireless noise-cancelling headphones, 30hr battery")
    draft = result.get_outputs()[-1].text  # refined title/description

    # --- Human-in-the-loop step ---
    print(f"\nProposed output:\n{draft}\n")
    approval = input("Approve? (yes/no): ").strip().lower()

    if approval == "yes":
        print("Approved. Final output:")
        print(draft)
    else:
        print("Rejected. Looping back to regenerate with feedback...")
        feedback = input("What should change? ")
        result = await workflow.run(
            f"Revise based on this feedback: {feedback}\nOriginal: {draft}"
        )
        print(result.get_outputs()[-1].text)

    await credential.close()

asyncio.run(main())