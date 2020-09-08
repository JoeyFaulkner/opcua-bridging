import logging
import asyncua
from asyncua import ua
from asyncua.ua.uatypes import VariantType
from asyncua.ua.uaprotocol_auto import NodeClass
from asyncua.ua.uaerrors import BadOutOfService, BadAttributeIdInvalid, BadInternalError, BadSecurityModeInsufficient
import datetime
from copy import deepcopy
import re

_logger = logging.getLogger('asyncua')


async def browse_nodes(node, to_export=False, path=None):
    """
    Build a nested node tree dict by recursion (filtered by OPC UA objects and variables).
    """
    node_id = node.nodeid.to_string()
    node_class = await node.read_node_class()
    children = []
    node_name = (await node.read_browse_name()).to_string()

    if path is None:
        path = [node_name]
    else:
        path.append(node_name)

    for child in await node.get_children():
        if await child.read_node_class() in [ua.NodeClass.Object, ua.NodeClass.Variable]:
            children.append(
                await browse_nodes(child, to_export=to_export, path=deepcopy(path))
            )
    if node_class != ua.NodeClass.Variable:
        var_type = None
    else:
        try:
            var_type = (await node.read_data_type_as_variant_type())
        except ua.UaError:
            _logger.warning('Node Variable Type could not be determined for %r', node)
            var_type = None
        try:
            current_value = await node.get_value()
        except (BadOutOfService, BadAttributeIdInvalid, BadInternalError, BadSecurityModeInsufficient):
            current_value = None
    output = {
        'id': node_id,
        'name': node_name,
        'cls': node_class.value,
        'type': var_type,
        'path': deepcopy(path)
    }
    if var_type:
        output['current_value'] = current_value

    if not to_export:
        output['node'] = node
        output['children'] = children
    else:
        if len(children) != 0:
            output['children'] = children
        if output['type']:
            output['type'] = VariantType(output['type']).name
        else:
            del output['type']
        if output['cls']:
            output['cls'] = NodeClass(output['cls']).name
        if output.get('current_value') and check_if_object_is_from_module(output['current_value'], asyncua):
            # if the current value is an asyncua object, which isnt yaml'd easily
            del output['current_value']

    return output


def check_if_object_is_from_module(obj_val, module):
    """
    function to see if the variable is an object that comes from the module, or any of its constituent parts are.
    :param obj_val:
    :param module:
    :return:
    """
    if isinstance(obj_val, list):
        return any(check_if_object_is_from_module(val, module) for val in obj_val)
    elif isinstance(obj_val, dict):
        return any(check_if_object_is_from_module(val, module) for val in obj_val.values())
    else:
        return getattr(obj_val, '__module__', '').startswith(module.__name__)


async def clone_nodes(nodes_dict, base_object, idx=0, node_id_prefix=''):
    mapping_list = []
    node_id = node_id_prefix + nodes_dict['id']
    # _logger.warning(f"{node_id} about to be added, idx={idx}")

    nodes_dict['name'] = fix_name(nodes_dict['name'], namespace_idx=idx)
    if nodes_dict['cls'] in [1, 'Object']:
        # node is an object

        if nodes_dict.get('children'):
            next_obj = await base_object.add_object(node_id, nodes_dict['name'])
            for child in nodes_dict['children']:
                mapping_list.extend(await clone_nodes(child, next_obj, idx=idx, node_id_prefix=node_id_prefix))
        else:
            return mapping_list
    elif nodes_dict['cls'] in [2, 'Variable']:
        # node is a variable
        next_var = await add_variable(base_object, nodes_dict, node_id)
        if next_var is None:
            return mapping_list
        mapped_id = next_var.nodeid.to_string()
        mapping_list.append((nodes_dict['id'], mapped_id))
    else:
        raise NotImplementedError
    return mapping_list


def fix_name(name, namespace_idx):
    if name.startswith('http://'):
        _logger.warning('urls as names do not work, stripping the http')
        name = name[len('http://'):]
    if re.search(r"^\d:", name):
        # checking if this name has the namespace in it, and if so changing it.
        name = f"{str(namespace_idx)}{name[1:]}"
    return name


async def add_variable(base_object, node_dict, node_id):
    node_name = node_dict['name']
    node_type = node_dict.get('type')
    # _logger.warning(node_name)
    _logger.warning(f"{node_name}{node_type}")
    if isinstance(node_type, str):
        node_type = VariantType[node_type]

    if node_dict.get('current_value'):
        original_val = node_dict['current_value']
    elif node_type in [VariantType.Boolean]:
        original_val = False
    elif node_type in [VariantType.Int16, VariantType.UInt16,
                       VariantType.Int32, VariantType.UInt32,
                       VariantType.Int64, VariantType.UInt64,
                       VariantType.Float]:
        original_val = 0
    elif node_type in [VariantType.String, VariantType.LocalizedText, VariantType.Byte]:
        original_val = ''
    elif node_type == VariantType.DateTime:
        original_val = datetime.datetime.today()
    elif node_type == VariantType.ExtensionObject:
        _logger.warning(f"Extension Objects are not supported by the bridge. Skipping")
        return None
    else:
        _logger.warning(f"node type {node_type} not covered by add_variable")
        original_val = 0.0
    try:
        return await base_object.add_variable(node_id, node_name, original_val, node_type)
    except:
        _logger.warning(f"{node_name}{node_type}")
        _logger.warning(node_type)
        exit(1)
