"""
Utility functions to iterate, set and get on deep dict objects.
"""


def iterate(deep_dict, path=None, to_return=None):
    """
    Iterate over the lowest level (the leaves) of self.agg_results,

    without needing a for loop for each level separately.
    Returns [ ([key1, key2, key3], value), (...), ... )]
    """
    if path is None:
        path = []
    if to_return is None:
        to_return = []
    if isinstance(deep_dict, dict):
        # pylint: disable=unused-variable
        for key in sorted_keys(deep_dict):
            pair = iterate(deep_dict[key], path + [key], to_return)
            # Avoid circular references on the way back
            if pair != to_return:
                to_return.append(pair)
        return to_return
    return path, deep_dict


def get_value(deep_dict, path):
    """Return deep_dict[path[0]][path[1]..."""
    value = deep_dict
    for key in path:
        value = value[key]
    return value


def set_value(deep_dict, path, value):
    """Set deep_dict[path[0]][path[1]]... = value"""
    obj = deep_dict
    for key in path[0:-1]:
        if key not in obj:
            obj[key] = {}
        obj = obj[key]
    key = path[-1]
    obj[key] = value


def del_value(deep_dict, path):
    """del() the value at path"""
    obj = deep_dict
    for key in path[0:-1]:
        obj = obj[key]
    key = path[-1]
    del obj[key]


def sorted_iter(a_dict):
    """Like dict.iteritems(), but sorts keys first."""
    keys = list(a_dict.keys())
    keys.sort()
    for key in keys:
        yield key, a_dict[key]


def sorted_keys(a_dict):
    """Like dict.keys(), but sorts keys first."""
    keys = list(a_dict.keys())
    keys.sort()
    for key in keys:
        yield key
