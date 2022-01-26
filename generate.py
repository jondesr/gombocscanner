from __future__ import annotations
from src.querybuilder import ResourceQueryGenerator
from gomboctypes.models import CfnResource
import pickle

capabilities_implementations = {resource.id:ResourceQueryGenerator.get_capabilities_implementations(resource.id) for resource in ResourceQueryGenerator(column_name="resource").asQuery("resource").parse_column_as_model("resource", CfnResource)}

with open('implementations.pkl', "wb") as file:
    pickle.dump(capabilities_implementations, file)