def trim_history(chat_history, max_len=8):
    return chat_history[-max_len:]


def summarize_memory(chat_history, client):
    prompt = f"""
Summarize this conversation briefly.

Focus on:
- Patient condition
- Key advice given
- Important discussion

Conversation:
{chat_history}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content