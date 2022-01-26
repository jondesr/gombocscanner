from __future__ import annotations
import graphene
from graphene_pydantic import PydanticObjectType
from gomboctypes.models import Capability
from src.querybuilder import CapabilityQueryGenerator
from src.implementation_plan import Recommendations_Model, Recommendations, ImplementationPlan
import src.cfn_lint

class CapabilityModel(PydanticObjectType):
    class Meta:
        model=Capability
    
    root_capability = graphene.Field('src.queries.CapabilityModel')

    @staticmethod
    def resolve_root_capability(parent: Capability, info):
        capabilities = CapabilityQueryGenerator(id=parent.id).provides_capability(capability_column="dest_c").asQuery("last(collect(dest_c)) as result").parse_column_as_model("result", Capability)
        
        if (len(capabilities)):
            return capabilities[0]
        else:
            return None

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
            currently_implements, supports_but_does_not_currently_implement = parsed_template.get_resource_internal_capabilities(logical_name)
            
            grouped_does_not_implement: dict[Capability, list[ImplementationPlan]] = {}
            for capability, implementation in supports_but_does_not_currently_implement:
                grouped_does_not_implement[capability] = grouped_does_not_implement.get(capability, []) + [implementation]

            # Don't show alternative implementations for capabilities already implemented
            capability_implementation_recommendations = [Recommendations(capability=capability, implementations=grouped_does_not_implement[capability]) for capability in grouped_does_not_implement.keys() if capability not in currently_implements]
            retval.append({"logical_name": logical_name, "currently_implements": sorted(currently_implements, key=lambda x: x.title), "supports_but_does_not_currently_implement": sorted(capability_implementation_recommendations, key=lambda x: x.capability.title)})
        
        return(retval)