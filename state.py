from typing import List, Optional, Union , TypedDict , Annotated , Literal
from pydantic import BaseModel , Field 
from langchain_core.messages import SystemMessage , HumanMessage , BaseMessage
import operator

class State(TypedDict):
    messages : Annotated[List[BaseMessage] , operator.add]
    user_id : int
    summary : str
    chunks : List[str]
    uuid : str
