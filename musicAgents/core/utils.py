from env_settings import load_env
from musicAgents.core.llm_provider import build_llm


load_env()


def get_llm(
    model="qwen-max",
    *,
    temperature: float = 0,
    timeout: int | None = None,
    task: str = "default",
):
    """Return the configured chat model for a task."""
    return build_llm(task=task, model=model, temperature=temperature, timeout=timeout)


def create_agent(llm, tools, system_prompt):
    """Create a simple prompt + model runnable with optional tools."""
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    if tools:
        llm = llm.bind_tools(tools)

    return prompt | llm
