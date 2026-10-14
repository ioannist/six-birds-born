"""Exact acquisition seed identities; no RNG draws or scored data reads.

Identity uniqueness is over (campaign, block, seed role), not invocations:
configurations deliberately reuse the same block. Kernel initialization and
dynamics also deliberately initialize ChaCha8 with the SAME base seed.
"""

U64_MAX = (1 << 64) - 1
EXACT_INTEGER_MAX = 1 << 53


def acquisition_identities(science):
    acquisition = science['acquisition']
    design = acquisition['seed_design']
    roles = design['distinct_identity_offsets']
    if roles != [0] + list(range(design['path_offset'], design['path_offset'] + design['path_count'])):
        raise ValueError('incomplete registered base/path seed identities')
    if len(set(roles)) != len(roles) or not all(type(x) is int for x in roles):
        raise ValueError('duplicate/noninteger registered seed offsets')
    identities = []
    for campaign in ('cross-term', 'competitor'):
        seeds = acquisition['grids']['v25-' + campaign]['seeds']
        recipe = design['campaigns'][campaign]
        expected = [recipe['base'] + recipe['spacing'] * k
                    for k in range(recipe['first_index'], recipe['last_index'] + 1)]
        if seeds != expected:
            raise ValueError('acquisition seeds differ from spaced recipe: ' + campaign)
        for k, seed in enumerate(seeds, recipe['first_index']):
            for offset in roles:
                value = seed + offset
                if type(value) is not int or not 0 <= value <= U64_MAX:
                    raise ValueError('acquisition seed outside u64')
                if value > EXACT_INTEGER_MAX or int(float(value)) != value:
                    raise ValueError('acquisition seed not exactly binary64 representable')
                identities.append({'campaign': campaign, 'block_index': k,
                                   'role': 'base' if offset == 0 else 'discovery_path',
                                   'path_index': None if offset == 0 else offset - design['path_offset'],
                                   'seed': value})
    values = [row['seed'] for row in identities]
    if len(values) != len(set(values)):
        raise ValueError('acquisition base/derived identities collide')
    return identities

