"""One resumable corrective evaluation: capture, units, inference, verdicts."""
import csv
import io
import json
from pathlib import Path
import subprocess

from .pipeline import begin, smoke
from .specification import Specification


def verdict_tables(output, results):
    """Readable views of saved inference, never a second statistical calculation."""
    rows = []
    for evaluation, result in results.items():
        rows.append({'evaluation': evaluation, 'endpoint': 'joint',
                     'status': result['joint']['status'], 'point': '', 'lower': '', 'upper': ''})
        rows.extend({'evaluation': evaluation, 'endpoint': name, 'status': row['status'],
                     'point': row['point'], 'lower': row['lower'], 'upper': row['upper']}
                    for name, row in result['paper_values'].items())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=['evaluation', 'endpoint', 'status', 'point', 'lower', 'upper'])
    writer.writeheader(); writer.writerows(rows)
    text = '| Evaluation | Endpoint | Status | Point | Lower | Upper |\n|---|---|---|---:|---:|---:|\n'
    text += ''.join('| ' + ' | '.join('' if value is None else str(value) for value in row.values()) + ' |\n' for row in rows)
    for name, content in [('verdicts.csv', buffer.getvalue()), ('verdicts.md', text),
                          ('verdicts.json', json.dumps(rows, indent=2) + '\n')]:
        target = Path(output) / name; temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(content); temporary.replace(target)
    return rows


def run(*, output, workers=1, specifications='specifications', synthetic=False, replicates=200):
    if workers < 1:
        raise ValueError('--workers must be positive')
    spec = Specification(specifications)
    output, _ = begin(spec, output, {'workflow': 'v25', 'mode': 'synthetic' if synthetic else 'registered',
                                  **({'replicates': replicates} if synthetic else {})})
    from born_ladder.reproduction.runs import exclusive_output, run_grid
    results = {}
    with exclusive_output(output):
        if synthetic:
            complete = smoke(output=output/'synthetic', specifications=spec.directory, replicates=replicates)
            directory = output/'synthetic'/complete['attempt']
            for evaluation in ('competitor', 'cross-term'):
                results[evaluation] = json.loads((directory/evaluation/'population.json').read_bytes())
        else:
            from .fresh import construct_fresh, infer_fresh
            if not Path('vendor/pica/target/release/runner').is_file():
                subprocess.run(['make', 'rust'], check=True)
            for evaluation in ('competitor', 'cross-term'):
                root = output/evaluation
                captured = run_grid(grid='v25-'+evaluation, output=root/'runs', workers=workers,
                                    specifications=spec.directory, capture=True)
                if captured['failed'] or captured['unlaunched']:
                    return {'status': 'incomplete', 'incomplete': True, 'stage': 'runs',
                            'evaluation': evaluation, 'details': captured}
                built = construct_fresh(runs=[root/'runs'], output=root/'units',
                                        evaluation=evaluation, specifications=spec.directory, workers=workers)
                if built['incomplete']:
                    return {'status': 'incomplete', 'incomplete': True, 'stage': 'units',
                            'evaluation': evaluation, 'details': built}
                collection = sorted((root/'units').glob('collection_*.json'))[-1]
                infer_fresh(units=collection, output=root/'evaluation', evaluation=evaluation,
                            specifications=spec.directory)
                complete = json.loads((root/'evaluation'/'complete.json').read_bytes())
                results[evaluation] = json.loads((root/'evaluation'/complete['attempt']/'population.json').read_bytes())
        rows = verdict_tables(output, results)
        return {'status': 'complete', 'mode': 'synthetic' if synthetic else 'registered',
                'verdicts': {e: r['joint']['status'] for e, r in results.items()},
                'table_rows': len(rows),
                'tables': [str(output/('verdicts'+suffix)) for suffix in ('.csv', '.md', '.json')]}
