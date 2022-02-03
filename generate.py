from __future__ import annotations
from src.querybuilder import ResourceQueryGenerator, CapabilityQueryGenerator
from gomboctypes.models import CfnResource, Capability
import pickle

capabilities_implementations = {resource.id:ResourceQueryGenerator.get_capabilities_implementations(resource.id) for resource in ResourceQueryGenerator(column_name="resource").asQuery("resource").parse_column_as_model("resource", CfnResource)}
capabilities = []

for capability in Capability.load_all():
    parent_response = CapabilityQueryGenerator(id=capability.id).provides_capability(capability_column="dest_c").asQuery("last(collect(dest_c)) as result").parse_column_as_model("result", Capability)

    if (len(parent_response)):
        capabilities.append((capability, parent_response[0]))
    
    else:
        capabilities.append((capability, None))

with open('implementations.pkl', "wb") as file:
    pickle.dump(capabilities_implementations, file)

with open('capabilities.pkl', 'wb') as file:
    pickle.dump(capabilities, file)