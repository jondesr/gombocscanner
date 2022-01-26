from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Union, Any, Tuple
import networkx
from gomboctypes.models import Capability, EdgeLabels, NodeLabels

import pickle
import src.implementation_plan

with open("implementations.pkl", "rb") as file:
    implementations: Dict[str, List[Tuple[Capability, networkx.DiGraph]]] = pickle.load(file)

CfnTemplate_Resource_Properties_Type = Union[str, Dict[str, Any], List[Dict[str, Any]]]

class CfnTemplate_Resource_Entry(BaseModel):
    Type: str = Field(...)
    Properties: Dict[str, CfnTemplate_Resource_Properties_Type] = Field(...)

class CfnTemplate(BaseModel):
    AWSTemplateFormatVersion: Optional[str]
    Description: Optional[str]
    Parameters: Optional[Dict[str, Dict]]
    Resources: Dict[str, CfnTemplate_Resource_Entry] = Field(...)
    Outputs: Optional[Dict[str, Dict]]

    def get_resource_internal_capabilities(self, resource_logical_name: str):
        implements: List[Capability] = []
        does_not_implement: List[Tuple[Capability, src.implementation_plan.ImplementationPlan]] = []
        resource_type = self.Resources[resource_logical_name].Type
        current_resource_graph = networkx.DiGraph()
        current_resource_graph.add_node(resource_type)

        if (resource_logical_name not in self.Resources):
            raise ValueError(f"Resource {resource_logical_name} doesn't exist in template")

        for property_name, property_value in self.Resources[resource_logical_name].Properties.items():
            self._recursively_add_property(current_resource_graph, resource_type, property_name, property_value)
        
        current_resource_graph = networkx.relabel.relabel_nodes(current_resource_graph, {node_id:(True, node_id) for node_id in current_resource_graph.nodes})

        for capability, implementation_graph in implementations[resource_type]:
            edges_not_implemented = [edge for edge in implementation_graph.edges if not current_resource_graph.has_edge(edge[0], edge[1])]
            
            # If implements capability, return it.
            if (not edges_not_implemented):
                implements.append(capability)

            # If does not implement the capability, return the actual delta to implement
            else:
                does_not_implement.append((capability, self.generate_implementation_plan(current_resource_graph, implementation_graph)))

        return((implements, does_not_implement))

    def _recursively_add_property(self, graph: networkx.DiGraph, ancestor_node_name: str, property_name: str, property_value: CfnTemplate_Resource_Properties_Type):
        if isinstance(property_value, str):
            graph.add_edge(ancestor_node_name, f"{ancestor_node_name}-{property_name}")

        elif isinstance(property_value, int):
            graph.add_edge(ancestor_node_name, f"{ancestor_node_name}-{property_name}")

        elif isinstance(property_value, list):
            for subproperty_value in property_value:
                self._recursively_add_property(graph, f"{ancestor_node_name}", property_name, subproperty_value)

        elif isinstance(property_value, dict):

            # If the entry is a CloudFormation reference i.e. {"Ref": "ResourceName"}
            if (list(map(lambda x: x.lower(), property_value.keys())) == ["ref"]):
                referenced_resource = self.Resources[list(property_value.values())[0]]
                
                for subproperty_name, subproperty_value in referenced_resource.Properties.items():
                    self._recursively_add_property(graph, f"{ancestor_node_name}-{property_name}", subproperty_name, subproperty_value)

            else:
                graph.add_edge(ancestor_node_name, f"{ancestor_node_name}-{property_name}", label=EdgeLabels.HAS_SUBPROPERTY)
                for subproperty_name, subproperty_value in property_value.items():
                    self._recursively_add_property(graph, f"{ancestor_node_name}-{property_name}", subproperty_name, subproperty_value)

        else:
            raise Exception(f"Unkonwn type {str(type(property_value))} for property {ancestor_node_name}-{property_name}")

    def generate_implementation_plan(self, current_resource_graph: networkx.Graph, implementation_graph: networkx.DiGraph):
        implementation_delta = implementation_graph.copy().to_directed()
        implementation_delta.remove_edges_from(current_resource_graph)
        implementation_delta.remove_nodes_from(list(networkx.isolates(implementation_delta)))        

        resources: List[src.implementation_plan.Resource] = []

        for resource_tuple in [node for node in networkx.topological_sort(implementation_delta.reverse()) if implementation_delta.nodes[node]["label"] == NodeLabels.CFN_RESOURCE]:
            resource_properties = []
            current_resource_properties_tuples = [node_tuple for node_tuple in implementation_delta.nodes if implementation_delta.nodes[node_tuple]["label"] == NodeLabels.CFN_PROPERTY and node_tuple[1].split("-")[0] == resource_tuple[1]]

            for property_tuple in sorted(current_resource_properties_tuples, key=lambda x: x[1]):
                uses_other_resources = [edge[1][1] for edge in implementation_delta.out_edges(property_tuple) if implementation_delta.edges[edge]["label"] == EdgeLabels.USES_OTHER_RESOURCE_TO]
                property_name = property_tuple[1].replace(f"{resource_tuple[1]}-", "")

                if (uses_other_resources):
                    resource_properties.append(src.implementation_plan.ResourceProperty(name=property_name, value=f"ARN of {{{uses_other_resources[0]}}}"))
                else:
                    resource_properties.append(src.implementation_plan.ResourceProperty(name=property_name, value=f"CONFIGURE APPROPRIATELY"))

            # Set the label depending whether it's an existing resource
            resource_action = src.implementation_plan.Action.ADD_PROPERTIES if resource_tuple[0] else src.implementation_plan.Action.NEW_RESOURCE
            resources.append(src.implementation_plan.Resource(type=resource_tuple[1], action=resource_action, properties=resource_properties))

        return src.implementation_plan.ImplementationPlan(resources=resources)