from __future__ import annotations
from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from graphene_pydantic import PydanticObjectType
import graphene

from gomboctypes.models import Capability

class ResourceProperty(BaseModel):
    name: str = Field(...)
    value: str = Field(...)

class ResourceProperty_Model(PydanticObjectType):
    class Meta:
        model=ResourceProperty

class Action(Enum):
    NEW_RESOURCE = "CREATE_NEW"
    ADD_PROPERTIES = "ADD_PROPERTIES"

resource_action_enum = graphene.Enum.from_enum(Action)

class Resource(BaseModel):
    type: str = Field(...)
    action: Action = Field(...)
    properties: List[ResourceProperty] = Field(...) 

class Resource_Model(PydanticObjectType):
    class Meta:
        model=Resource

class ImplementationPlan(BaseModel):
    resources: List[Resource] = Field(...)

class ImplementationPlan_Model(PydanticObjectType):
    class Meta:
        model=ImplementationPlan

class CapabilityModel(PydanticObjectType):
    class Meta:
        model=Capability

class Recommendations(BaseModel):
    capability: Capability = Field(...)
    implementations: List[ImplementationPlan] = Field(...)

class Recommendations_Model(PydanticObjectType):
    class Meta:
        model=Recommendations