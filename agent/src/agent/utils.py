import os
from dotenv import load_dotenv
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI



load_dotenv()
logging.basicConfig(level=logging.INFO)
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)


llms = {"google" : {"fast": ChatGoogleGenerativeAI(project = project_id , model="gemini-2.5-flash"),
                     "expert": ChatGoogleGenerativeAI(project = project_id ,model="gemini-2.5-pro"), },
        "openai" : {"fast" : ChatOpenAI(model = "gpt-4o-mini"),
                    "expert" : ChatOpenAI(model = "gpt-4o")},
        # "claude" : {"fast" : ChatAnthropic(model = "claude-3-opus-latest"),
        #             "expert" : ChatAnthropic(model = "claude-3-opus-latest")},
                        }



PROMPT = """
Legal AI Agent
"""
