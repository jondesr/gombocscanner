from __future__ import annotations
from functools import lru_cache
import graphene
import pickle
from typing import Dict, List, Tuple, Optional
from graphene_pydantic import PydanticObjectType
from gomboctypes.models import Capability
from src.querybuilder import CapabilityQueryGenerator
from src.implementation_plan import Recommendations_Model, Recommendations, ImplementationPlan
import src.settings
import src.cfn_lint

settings = src.settings.Settings()

@lru_cache(maxsize=None)
def _load_capabilities_from_pickle() -> List[Tuple[Capability, Optional[Capability]]]:
    with open("capabilities.pkl", "rb") as file:
        return pickle.load(file)

def _get_capability_from_pickle(id: str):
    matches = list(filter(lambda x: x[0].id == id, _load_capabilities_from_pickle()))

    if (len(matches) != 1):
        raise Exception(f"Was expecting 1 Capability matching id {id}, but found {matches}")

    return matches[0]

class CapabilityModel(PydanticObjectType):
    class Meta:
        model=Capability
    
    root_capability = graphene.Field('src.queries.CapabilityModel')

    @staticmethod
    def resolve_root_capability(parent: Capability, info):

        if (settings.DATASOURCE == src.settings.DataSource.NEO4J.value):
            capabilities = CapabilityQueryGenerator(id=parent.id).provides_capability(capability_column="dest_c").asQuery("last(collect(dest_c)) as result").parse_column_as_model("result", Capability)
            
            if (len(capabilities)):
                return capabilities[0]
            else:
                return None

        elif (settings.DATASOURCE == src.settings.DataSource.PICKLE.value):
            capability_tuple = _get_capability_from_pickle(parent.id)
            return capability_tuple[1]
        
        else:
            raise Exception(f"Unexpected Datasource: {settings.DATASOURCE}")

class ResourceCapabilityReport(graphene.ObjectType):
    logical_name = graphene.String(required=True)
    currently_implements = graphene.List(CapabilityModel, required=True)
    supports_but_does_not_currently_implement = graphene.List(graphene.NonNull(Recommendations_Model), required=True)

class Query(graphene.ObjectType):
    scan_cloudformation_template = graphene.List(graphene.NonNull(ResourceCapabilityReport), required=True, template=graphene.String(required=True))

    @staticmethod
    def resolve_scan_cloudformation_template(root, info, template: str):
        retval = []
        parsed_template = src.cfn_lint.CfnTemplate.parse_raw(template)

        for logical_name in parsed_template.Resources.keys():
            recommendations_dict: Dict[str, Recommendations] = {}
            currently_implements, supports_but_does_not_currently_implement = parsed_template.get_resource_internal_capabilities(logical_name)
            
            for capability, implementation in supports_but_does_not_currently_implement:    
                if (capability.id not in recommendations_dict):
                    recommendations_dict[capability.id] = Recommendations(capability=capability, implementations=[])

                recommendations_dict[capability.id].implementations.append(implementation)

            # Don't show alternative implementations for capabilities already implemented
            retval.append({"logical_name": logical_name, "currently_implements": sorted(currently_implements, key=lambda x: x.title), "supports_but_does_not_currently_implement": sorted(recommendations_dict.values(), key=lambda x: x.capability.title)})
        
        return(retval)