from __future__ import annotations
import glob
from src.cfn_lint import CfnTemplate

for filename in glob.glob('examples/*.json'):
    template = CfnTemplate.parse_file(filename)
    for logical_resource_name in template.Resources.keys():
        currently_implements, supports_but_does_not_currently_implement = template.get_resource_internal_capabilities(logical_resource_name)
        print(currently_implements)