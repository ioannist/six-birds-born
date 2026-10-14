"""Resume equality for numerical contracts; source and pool size are annotations."""
from pathlib import Path


def scientific_specification_file(name):
    """Interface examples and paper display selectors are not numerical inputs."""
    filename=Path(name).name
    return filename!='paper_numbers.json' and not filename.endswith('.example.json')


def numeric_plan(plan):
    result={key:value for key,value in plan.items() if key not in ('source_code','source_hashes','code','admission_workers')}
    if isinstance(result.get('specifications'),list):
        result['specifications']=[row for row in result['specifications']
                                  if not isinstance(row,dict) or 'path' not in row
                                  or scientific_specification_file(row['path'])]
    return result
