import os
import asyncio
from dotenv import load_dotenv
load_dotenv()
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_classic.memory import ConversationBufferMemory

class SteadyAssistant:
    def __init__(self, log_widget, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        self.log_widget = log_widget
        
        if self.api_key:
            self.llm = ChatOpenAI(
                model="llama3.1-8b", 
                openai_api_key=self.api_key, 
                openai_api_base="https://api.cerebras.ai/v1",
                temperature=0.7
            )
        else:
            self.llm = None

        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        self.system_prompt = "You are the SteadyFlow AI Assistant, a high-performance terminal companion."

    async def initialize(self):
        """No complex initialization needed for basic chat."""
        if not self.llm:
            self.log_widget.write("[red]Warning: CEREBRAS_API_KEY not found in .env. Chat will be disabled.[/]")
        else:
            self.log_widget.write("[green]SteadyFlow AI Assistant Ready.[/]")

    async def process_input(self, user_input: str):
        """Processes user input using basic LLM call."""
        if not self.llm:
            return "Error: API key missing. Please add CEREBRAS_API_KEY to your .env file."
            
        try:
            # Get conversation history
            history = self.memory.load_memory_variables({})["chat_history"]
            
            messages = [SystemMessage(content=self.system_prompt)]
            messages.extend(history)
            messages.append(HumanMessage(content=user_input))
            
            response = await self.llm.ainvoke(messages)
            
            # Save to memory
            self.memory.save_context({"input": user_input}, {"output": response.content})
            
            return response.content
        except Exception as e:
            return f"Assistant Error: {str(e)}"

    async def shutdown(self):
        pass
