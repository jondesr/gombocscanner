from __future__ import annotations
from typing import Optional, Tuple, cast, Dict
from gomboctypes.models import Capability, NodeLabels, EdgeLabels, Relation, UseCase
from neo4j import Neo4jDriver, GraphDatabase
import networkx

from typing import List
from src.settings import Settings

settings = Settings()
driver = cast(Neo4jDriver, GraphDatabase.driver(settings.NEO4J_URL, auth=(settings.NEO4j_USER, settings.NEO4j_PASSWORD)))

class QueryGenerator():
    def __init__(self, preceding_cypher_string: str = "", column_name: str = "", id: str = "", hide_label: bool = False):
        if (hide_label):
            label = ""
        else:
            label = self.get_node_label().value

        if (id):
            self._cypher_string = f"{preceding_cypher_string}({column_name}{label} {{id: '{id}'}})"
        else:
            self._cypher_string = f"{preceding_cypher_string}({column_name}{label})"

    @staticmethod
    def get_node_label() -> NodeLabels:
        raise NotImplementedError

    def asQuery(self, columns: str):
        return Query(f"MATCH {self._cypher_string} RETURN {columns}")

    def asFragment(self):
        return self._cypher_string

class Query():
    def __init__(self, querystring: str):
        self._querystring = querystring

    def union(self, other: Query):
        return Query(self._querystring + " UNION " + other._querystring)

    def parse_column_as_model(self, column_name: str, pydantic_model):
        with driver.session() as session:
            print(f"Executing Query: {self._querystring}")
            result = session.run(self._querystring)
            return [pydantic_model.parse_obj(record[column_name]._properties) for record in result if record[column_name]]

    def parse_column_as_relation(self, column_name: str):
        with driver.session() as session:
            print(f"Executing Query: {self._querystring}")
            result = session.run(self._querystring)
            records = [record[column_name] for record in result]
            return [Relation(
                source_label=NodeLabels.parse_from_iterable(record.start_node.labels),
                source_id=record.start_node._properties["id"],
                relation_label=EdgeLabels.parse_string(record.type),
                target_label=NodeLabels.parse_from_iterable(record.end_node.labels),
                target_id=record.end_node._properties["id"]) for record in records]

class UseCaseQueryGenerator(QueryGenerator):

    @staticmethod
    def get_node_label():
        return NodeLabels.USE_CASE

    def to_implementing_resource_or_property(self, column_name: str = "", id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.CAN_BE_USED_TO.value}]-", column_name=column_name, id=id, hide_label=True)

    def to_implementing_property(self, column_name: str = "", id: str = ""):
        return PropertyQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.CAN_BE_USED_TO.value}]-", column_name=column_name, id=id)

    def to_using_resource_or_property(self, column_name: str = "", id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.USES_OTHER_RESOURCE_TO.value}]-", column_name=column_name, id=id, hide_label=True)

    def capabilities_directly_from_usecase(self, capability_column: str = "", capability_id: str = ""):
        return CapabilityQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.PROVIDES_CAPABILITY.value}]->", column_name=capability_column, id=capability_id)

    def capabilities_from_descendent_properties(self, capability_column: str = "", capability_id: str = ""):
        return self.to_implementing_resource_or_property().include_resource_adding_capabilities().include_subproperties().provides_capability(capability_column=capability_column, capability_id=capability_id)

    def paths_to_capabilities(self, capability_column: str = "", capability_id: str = ""):
        return [

            # Capabilities directly from UseCaes, add a pattern match to the Resource providing the UseCase
            self.to_implementing_resource_or_property().to_resource_from_property().asFragment() + "," + self.capabilities_directly_from_usecase(capability_column=capability_column, capability_id=capability_id).asFragment(),

            # Capabilities provided by Subproperties of the propety CAN_BE_USED_TO the usecase (include the resource)
            ResourceQueryGenerator(column_name="used_resource").include_subproperties(resource_column="enabling_usecase").include_subproperties().provides_capability(capability_column="capability").asFragment() + "," + self.to_implementing_resource_or_property(column_name="enabling_usecase").asFragment(),

            # Capabilities provided by Properties of Resource Adding capabilities
            self.to_implementing_resource_or_property().to_resource_from_property().include_subproperties_only_from_adds_capability_to_resource().provides_capability(capability_column="capability").asFragment()
        ]

    @staticmethod
    def capabilities_provided(usecase_id: str):
        capabilities_directly_from_usecase = UseCaseQueryGenerator(id=usecase_id).capabilities_directly_from_usecase("capability").asQuery("capability")
        capabilities_from_descendent_properties = UseCaseQueryGenerator(id=usecase_id).capabilities_from_descendent_properties("capability").asQuery("capability")

        return capabilities_directly_from_usecase.union(capabilities_from_descendent_properties).parse_column_as_model("capability", Capability)

    @staticmethod
    def paths_to_implement_capabilities(usecase_id: str):
        direct_from_usecase = UseCaseQueryGenerator(preceding_cypher_string=f"", id=usecase_id)

class CapabilityQueryGenerator(QueryGenerator):

    @staticmethod
    def get_node_label():
        return NodeLabels.CAPABILITY

    def provides_capability(self, capability_column: str = "", capability_id: str = ""):
        return CapabilityQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.PROVIDES_CAPABILITY.value}*]->", column_name=capability_column, id=capability_id)

class PropertyQueryGenerator(QueryGenerator):

    @staticmethod
    def get_node_label():
        return NodeLabels.CFN_PROPERTY

class ResourceQueryGenerator(QueryGenerator):

    @staticmethod
    def get_node_label():
        return NodeLabels.CFN_RESOURCE

    def include_subproperties(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]->", hide_label=True, column_name=resource_column, id=resource_id)

    def include_resource_adding_capabilities(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.ADDS_CAPABILITIES_TO_RESOURCE.value}*0..]-", hide_label=True, column_name=resource_column, id=resource_id)

    def include_resource_from_property(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]-", column_name=resource_column, id=resource_id, hide_label=True)

    def to_resource_from_property(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]-", column_name=resource_column, id=resource_id)

    def adds_capabilities_to_resource(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.ADDS_CAPABILITIES_TO_RESOURCE.value}]->", column_name=resource_column, id=resource_id)

    def can_be_used_to(self, usecase_column: str = "", usecase_id: str = ""):
        return UseCaseQueryGenerator(preceding_cypher_string=f"{self._cypher_string}-[{EdgeLabels.CAN_BE_USED_TO.value}]->", column_name=usecase_column, id=usecase_id)

    def include_subproperties_including_from_adds_capability_to_resource(self):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.ADDS_CAPABILITIES_TO_RESOURCE.value}*0..]-()-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]->", hide_label=True)

    def include_subproperties_only_from_same_resource(self):
        return ResourceQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]->", hide_label=True)

    def include_subproperties_only_from_adds_capability_to_resource(self):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.ADDS_CAPABILITIES_TO_RESOURCE.value}]-()-[{EdgeLabels.HAS_SUBPROPERTY.value}*0..]-", hide_label=True)

    def to_property_adding_capabilities(self, resource_column: str = "", resource_id: str = ""):
        return ResourceQueryGenerator(f"{self._cypher_string}<-[{EdgeLabels.ADDS_CAPABILITIES_TO_RESOURCE.value}]-", column_name=resource_column, id=resource_id, hide_label=True)

    def enables_internal_capability(self, capability_column: str = "", capability_id: str = ""):
        return CapabilityQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.ENABLES_INTERNAL_CAPABILITY.value}]->", column_name=capability_column, id=capability_id)

    def provides_capability(self, capability_column: str = "", capability_id: str = ""):
        return CapabilityQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.PROVIDES_CAPABILITY.value}]->", column_name=capability_column, id=capability_id)

    def uses_other_resource_to(self, usecase_column: str = "", usecase_id: str = ""):
        return UseCaseQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.USES_OTHER_RESOURCE_TO.value}]->", column_name=usecase_column, id=usecase_id)

    def has_subproperty(self, property_column: str = "", property_id: str = ""):
        return PropertyQueryGenerator(f"{self._cypher_string}-[{EdgeLabels.HAS_SUBPROPERTY.value}*1..]->", column_name=property_column, id=property_id)

    @staticmethod
    def relations(resource_id: str):
        query = (f"MATCH (resource{NodeLabels.CFN_RESOURCE.value} {{id:'{resource_id}'}})-[{EdgeLabels.HAS_SUBPROPERTY.value}*1..]->(property{NodeLabels.CFN_PROPERTY.value})-[relation]-(other) " +
            f"WHERE type(relation) <> '{EdgeLabels.HAS_SUBPROPERTY.value.replace(':','')}' "
            f"RETURN resource, property, relation, other " +
            f"UNION " +
            f"MATCH (resource{NodeLabels.CFN_RESOURCE.value} {{id:'{resource_id}'}})-[relation]-(other) " +
            f"WHERE type(relation) <> '{EdgeLabels.HAS_SUBPROPERTY.value.replace(':','')}' "
            f"RETURN resource, null as property, relation, other")
        
        return Query(query).parse_column_as_relation("relation")

    @staticmethod
    def internal_capabilities_implementations_cypher_query(resource_id: str):
        this_resource = ResourceQueryGenerator(id=resource_id)
        query_fragments: List[Dict[str, str]] = []

        # Resource -> Properties -> Capabilities
        query_fragments.append({
            "internal_resource_configuration": this_resource.include_subproperties().enables_internal_capability(capability_column="capability").asFragment()
        })

        # Resource -> Properties -> Usecases ...
        query_fragments += [{
            "internal_resource_configuration": this_resource.include_subproperties().uses_other_resource_to(usecase_column="usecase").asFragment(),
            "other_resource_configuration": path} for path in UseCaseQueryGenerator(column_name="usecase").paths_to_capabilities(capability_column="capability")]

        to_primary_resource = ResourceQueryGenerator(column_name="to_primary_resource", hide_label=True)
        properties_in_resource_providing_capabilities = to_primary_resource.include_resource_from_property().include_subproperties_including_from_adds_capability_to_resource()

        # Resource <- Resource_Adding_capabilities -> Properties -> Capabilities
        query_fragments += [{
            "internal_resource_configuration": this_resource.asFragment(),
            "other_resource_configuration": properties_in_resource_providing_capabilities.enables_internal_capability(capability_column="capability").asFragment() + "," + to_primary_resource.adds_capabilities_to_resource(resource_id=resource_id).asFragment()
        }]

        # Resource <- Resource Adding Capabilities -> Properties -> Usecases...
        query_fragments += [{
            "internal_resource_configuration": this_resource.asFragment(),
            "other_resource_configuration": path + "," + to_primary_resource.adds_capabilities_to_resource(resource_id=resource_id).asFragment()} for path in properties_in_resource_providing_capabilities.uses_other_resource_to(usecase_column="usecase").paths_to_capabilities(capability_column="capability")]

        query_statements: List[str] = []

        for fragments in query_fragments:
            if "other_resource_configuration" in fragments:                
                query_statements.append(f"MATCH internal_resource_configuration={fragments['internal_resource_configuration']}, other_resource_configuration={fragments['other_resource_configuration']} RETURN internal_resource_configuration, other_resource_configuration, capability")
            else:
                query_statements.append(f"MATCH internal_resource_configuration={fragments['internal_resource_configuration']} RETURN internal_resource_configuration, NULL as other_resource_configuration, capability")

        return " UNION ".join(query_statements)

    @staticmethod
    def get_capabilities_implementations(resource_id: str):
        capability_implementations: List[Tuple[Capability, networkx.DiGraph]] = []

        with driver.session() as session:
            print(f"Running query: {ResourceQueryGenerator.internal_capabilities_implementations_cypher_query(resource_id)}")

            for record in session.run(ResourceQueryGenerator.internal_capabilities_implementations_cypher_query(resource_id)):
                capability = Capability.parse_obj(record["capability"]._properties)
                graph = networkx.DiGraph()

                for node in record["internal_resource_configuration"].nodes:
                    if (NodeLabels.parse_from_iterable(node.labels) == NodeLabels.CFN_RESOURCE):
                        graph.add_node((True, node._properties["id"]), label=NodeLabels.CFN_RESOURCE)

                for relationship in record["internal_resource_configuration"].relationships:
                    if (EdgeLabels.parse_string(relationship.type) != EdgeLabels.ENABLES_INTERNAL_CAPABILITY):
                        start_node_properties = relationship.start_node._properties
                        end_node_properties = relationship.end_node._properties

                        start_node_label = NodeLabels.parse_from_iterable(relationship.start_node.labels)
                        end_node_label = NodeLabels.parse_from_iterable(relationship.end_node.labels)

                        start_node_tuple = (start_node_label in [NodeLabels.CFN_RESOURCE, NodeLabels.CFN_PROPERTY], start_node_properties["id"])
                        end_node_tuple = (end_node_label in [NodeLabels.CFN_RESOURCE, NodeLabels.CFN_PROPERTY], end_node_properties["id"])

                        graph.add_edge(start_node_tuple, end_node_tuple, label=EdgeLabels.parse_string(relationship.type))
                        graph.nodes[start_node_tuple]["label"] = start_node_label
                        graph.nodes[end_node_tuple]["label"] = end_node_label

                if (record.get("other_resource_configuration")):
                    for relationship in record["other_resource_configuration"]:
                        if(EdgeLabels.parse_string(relationship.type) != EdgeLabels.PROVIDES_CAPABILITY):
                            start_node_tuple = (False, relationship.start_node._properties["id"])
                            end_node_tuple = (False, relationship.end_node._properties["id"])

                            graph.add_edge(start_node_tuple, end_node_tuple, label=EdgeLabels.parse_string(relationship.type))
                            graph.nodes[start_node_tuple]["label"] = NodeLabels.parse_from_iterable(relationship.start_node.labels)
                            graph.nodes[end_node_tuple]["label"] = NodeLabels.parse_from_iterable(relationship.end_node.labels)

                # Delete Usecases and connect the nodes that uses and can_be_used_to directly
                for usecase_id in [node_id for node_id in graph.nodes if graph.nodes[node_id]["label"] == NodeLabels.USE_CASE]:
                    usecase_in_edges = [edge for edge in graph.in_edges(usecase_id)]
                    can_be_used_to_node_id = [edge[0] for edge in usecase_in_edges if graph.edges[edge]["label"] == EdgeLabels.CAN_BE_USED_TO][0]
                    usecase_node_id = usecase_in_edges[0][1]

                    for using_other_resource_to in [edge for edge in usecase_in_edges if graph.edges[edge]["label"] == EdgeLabels.USES_OTHER_RESOURCE_TO]:
                        graph.add_edge(using_other_resource_to[0], can_be_used_to_node_id, label=EdgeLabels.USES_OTHER_RESOURCE_TO)

                    graph.remove_node(usecase_node_id)

                capability_implementations.append((capability, graph))

        return(capability_implementations)